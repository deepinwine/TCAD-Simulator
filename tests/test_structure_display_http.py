"""Additive display endpoints preserve formal execution and persistence."""
import base64
import copy
import json
import sys
import unittest
from unittest.mock import patch

import numpy as np
import tcad_simulator as tcad
from tests import test_structure_editor_http as editor_tests
from tests.test_structure_display_geometry import decode_mesh


class StructureDisplayHTTPTests(unittest.TestCase):
    def setUp(self):
        # Exercise the actual in-process worker, so execute guards prove that
        # read endpoints never invoke processes rather than patching a parent.
        with patch.object(tcad, '_tcad_can_spawn_webui_worker', return_value=False), \
             patch.object(tcad, '_tcad_can_fork_webui_worker', return_value=False):
            editor_tests.StructureEditorHTTPTests.setUp(self)
        self.assertIsInstance(next(iter(self.manager.sessions.values())).process, tcad._ThreadWorkerProcess)
    _request = editor_tests.StructureEditorHTTPTests._request
    request = editor_tests.StructureEditorHTTPTests.request

    def fixture(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '同材料展示', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 10}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
            {'name': 'Structure Etch', 'params': {'material': 'Silicon Dioxide', 'depth_nm': 5}},
        ]}})
        self.request('POST', '/api/run/all', {})

    def manifest(self):
        return self.request('GET', '/api/structure/display/manifest')['result']

    def display_voxels(self):
        manifest = self.manifest()
        shape = tuple(manifest['domain']['grid_shape'])
        material = np.empty(shape, dtype=np.uint16)
        owners = np.empty(shape, dtype=np.uint32)
        for index in range(shape[0]):
            section = self.request('GET', '/api/structure/display/slice?revision={}&axis=X&index={}'.format(
                manifest['revision'], index))['result']
            material[index] = np.frombuffer(base64.b64decode(section['material']['data_b64']), '<u2').reshape(section['shape']).T
            owners[index] = np.frombuffer(base64.b64decode(section['owner']['data_b64']), '<u4').reshape(section['shape']).T
        return manifest, material, owners

    def worker_history(self):
        process = next(iter(self.manager.sessions.values())).process
        frame = sys._current_frames()[process._thread.ident]
        while frame:
            if frame.f_code.co_name == '_webui_worker_main':
                return frame.f_locals['undo_stack'], frame.f_locals['redo_stack']
            frame = frame.f_back
        self.fail('Worker history frame unavailable')

    def test_removed_built_step_saves_and_loads_as_unknown_without_changing_grid(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '删除来源', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'material': 'Silicon', 'thickness_nm': 20}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
        ]}})
        self.request('POST', '/api/run/all', {})
        steps = self.request('GET', '/api/init')['result']['recipe']
        before, grid, owners = self.display_voxels()
        removed_id = steps[1]['step_id']
        removed_owner = next(int(owner) for owner, identity in before['owner_step_ids'].items() if identity == removed_id)
        expected = owners.copy()
        expected[owners == removed_owner] = 0
        with patch.object(tcad.StructureDepositStep, 'execute', side_effect=AssertionError('Unexpected execute')), \
             patch.object(tcad.StructureWaferStep, 'execute', side_effect=AssertionError('Unexpected execute')):
            remaining = self.request('POST', '/api/recipe/remove', {'index': 1})['result']
            saved = self.request('POST', '/api/recipe/save', {'name': '删除来源'})['result']
            self.request('POST', '/api/recipe/new', {'name': '切换后加载'})
            loaded = self.request('POST', '/api/recipe/load', {'id': saved['id']})['result']
            after, restored_grid, restored_owners = self.display_voxels()
        self.assertEqual([steps[0]['step_id']], [step['step_id'] for step in remaining])
        self.assertEqual([steps[0]['step_id']], [step['step_id'] for step in loaded['recipe']])
        np.testing.assert_array_equal(grid, restored_grid)
        np.testing.assert_array_equal(expected, restored_owners)
        self.assertEqual({owner: identity for owner, identity in before['owner_step_ids'].items() if identity != removed_id},
                         after['owner_step_ids'])
        self.assertTrue(any(group['owner_id'] == 0 and group['step_id'] is None for group in after['groups']))

    def test_removal_preserves_other_owner_of_the_same_material(self):
        self.fixture()
        steps = self.request('GET', '/api/init')['result']['recipe']
        before, grid, owners = self.display_voxels()
        removed_id, retained_id = steps[1]['step_id'], steps[2]['step_id']
        removed_owner = next(int(owner) for owner, identity in before['owner_step_ids'].items() if identity == removed_id)
        retained_owner = next(int(owner) for owner, identity in before['owner_step_ids'].items() if identity == retained_id)
        self.request('POST', '/api/recipe/remove', {'index': 1})
        after, actual_grid, actual_owners = self.display_voxels()
        expected = owners.copy()
        expected[owners == removed_owner] = 0
        np.testing.assert_array_equal(grid, actual_grid)
        np.testing.assert_array_equal(expected, actual_owners)
        self.assertEqual(after['owner_step_ids'][str(retained_owner)], retained_id)
        self.assertTrue(np.all(actual_owners[owners == retained_owner] == retained_owner))
        self.assertGreater(after['revision'], before['revision'])
        self.assertNotIn(removed_id, after['owner_step_ids'].values())

    def test_deleted_owner_stays_unknown_when_a_retained_direct_timeline_is_restored(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '保留检查点', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 20}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
        ]}})
        self.request('POST', '/api/run/all', {})
        # A direct checkpoint for step 1 can contain geometry made earlier by step 2.
        self.request('POST', '/api/run/step', {'index': 1})
        steps = self.request('GET', '/api/init')['result']['recipe']
        before, grid, owners = self.display_voxels()
        removed_id = steps[2]['step_id']
        removed_owner = next(int(owner) for owner, identity in before['owner_step_ids'].items() if identity == removed_id)
        expected = owners.copy()
        expected[owners == removed_owner] = 0
        self.request('POST', '/api/recipe/remove', {'index': 2})
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        self.assertTrue(timeline['items'][1]['snapshot_valid'])
        restored = self.request('POST', '/api/timeline/restore', {'index': 1})['result']
        self.assertEqual(restored['timeline']['current'], 1)
        after, actual_grid, actual_owners = self.display_voxels()
        np.testing.assert_array_equal(grid, actual_grid)
        np.testing.assert_array_equal(expected, actual_owners)
        self.assertNotIn(removed_id, after['owner_step_ids'].values())
        saved = self.request('POST', '/api/recipe/save', {'name': '检查点加载'})['result']
        self.request('POST', '/api/recipe/new', {'name': '检查点切换'})
        self.request('POST', '/api/recipe/load', {'id': saved['id']})
        _, loaded_grid, loaded_owners = self.display_voxels()
        np.testing.assert_array_equal(grid, loaded_grid)
        np.testing.assert_array_equal(expected, loaded_owners)

    def test_undo_restores_valid_original_recipe_and_redo_restores_deleted_source(self):
        self.fixture()
        original = self.request('GET', '/api/init')['result']['recipe']
        self.request('POST', '/api/run/step', {'index': 1})
        before, grid, owners = self.display_voxels()
        deleted_id = original[1]['step_id']
        deleted_owner = next(int(owner) for owner, identity in before['owner_step_ids'].items() if identity == deleted_id)
        self.request('POST', '/api/recipe/remove', {'index': 1})
        undone = self.request('POST', '/api/undo', {})['result']
        self.assertTrue(undone['undone'])
        self.assertEqual([step['step_id'] for step in original], [step['step_id'] for step in undone['recipe']])
        restored = self.manifest()
        self.assertEqual(restored['owner_step_ids'][str(deleted_owner)], deleted_id)
        redone = self.request('POST', '/api/redo', {})['result']
        self.assertTrue(redone['redone'])
        self.assertNotIn(deleted_id, [step['step_id'] for step in redone['recipe']])
        after, redone_grid, redone_owners = self.display_voxels()
        expected = owners.copy()
        expected[owners == deleted_owner] = 0
        np.testing.assert_array_equal(grid, redone_grid)
        np.testing.assert_array_equal(expected, redone_owners)
        self.assertNotIn(deleted_id, after['owner_step_ids'].values())
        saved = self.request('POST', '/api/recipe/save', {'name': '删除后历史加载'})['result']
        self.request('POST', '/api/recipe/new', {'name': '历史切换'})
        self.request('POST', '/api/recipe/load', {'id': saved['id']})

    def test_incremental_same_parameter_prefix_retires_deleted_identity(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '同参数缓存', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 20}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
            {'name': 'Structure Deposit', 'params': {'material': 'Silicon Dioxide', 'thickness_nm': 10}},
        ]}})
        self.request('POST', '/api/run/to', {'index': 1})
        before, prefix_grid, prefix_owners = self.display_voxels()
        steps = self.request('GET', '/api/init')['result']['recipe']
        removed_id = steps[1]['step_id']
        removed_owner = next(int(owner) for owner, identity in before['owner_step_ids'].items() if identity == removed_id)
        self.request('POST', '/api/run/all', {})
        self.request('POST', '/api/recipe/remove', {'index': 1})
        # Execution signatures match, so this restores the old step-1 prefix.
        with patch.object(tcad.StructureDepositStep, 'execute', side_effect=AssertionError('Unexpected execute')), \
             patch.object(tcad.StructureWaferStep, 'execute', side_effect=AssertionError('Unexpected execute')):
            self.request('POST', '/api/run/to', {'index': 1})
        after, actual_grid, actual_owners = self.display_voxels()
        expected = prefix_owners.copy()
        expected[prefix_owners == removed_owner] = 0
        np.testing.assert_array_equal(prefix_grid, actual_grid)
        np.testing.assert_array_equal(expected, actual_owners)
        self.assertNotIn(removed_id, after['owner_step_ids'].values())
        saved = self.request('POST', '/api/recipe/save', {'name': '增量缓存加载'})['result']
        self.request('POST', '/api/recipe/new', {'name': '增量切换'})
        self.request('POST', '/api/recipe/load', {'id': saved['id']})

    def test_failed_source_removal_preserves_recipe_grid_source_and_history(self):
        from structure_cad.display_provenance import DisplayProvenance
        self.fixture()
        self.request('POST', '/api/run/step', {'index': 1})
        self.request('POST', '/api/undo', {})
        before = self.request('GET', '/api/init')['result']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        manifest, grid, owners = self.display_voxels()
        with patch.object(DisplayProvenance, 'forget_step', side_effect=MemoryError('removal preflight failure')):
            rejected = self.request('POST', '/api/recipe/remove', {'index': 1}, ok=False)
        self.assertIn('removal preflight failure', rejected['error'])
        after = self.request('GET', '/api/init')['result']
        for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
        after_manifest, actual_grid, actual_owners = self.display_voxels()
        self.assertEqual(manifest, after_manifest)
        np.testing.assert_array_equal(grid, actual_grid)
        np.testing.assert_array_equal(owners, actual_owners)
        self.assertTrue(self.request('POST', '/api/redo', {})['result']['redone'])

    def test_timeline_unknown_identity_is_rejected_after_known_source_deletion(self):
        self.fixture()
        self.request('POST', '/api/recipe/remove', {'index': 2})
        before = self.request('GET', '/api/init')['result']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        manifest, grid, owners = self.display_voxels()
        original_load = tcad._tcad_snapshot_load_maybe
        foreign_id = tcad.StructureWaferStep(tcad.MaterialDatabase()).step_id

        def damaged_snapshot(ref):
            snapshot = copy.deepcopy(original_load(ref))
            snapshot['display_step_ids'][1] = foreign_id
            return snapshot

        with patch.object(tcad, '_tcad_snapshot_load_maybe', side_effect=damaged_snapshot):
            rejected = self.request('POST', '/api/timeline/restore', {'index': 1}, ok=False)
        self.assertEqual(rejected['code'], 'restore_failed')
        self.assertIn('identity mapping', rejected['error'])
        self.assertTrue(rejected['rolled_back'])
        after = self.request('GET', '/api/init')['result']
        for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
        actual_manifest, actual_grid, actual_owners = self.display_voxels()
        self.assertEqual(manifest, actual_manifest)
        np.testing.assert_array_equal(grid, actual_grid)
        np.testing.assert_array_equal(owners, actual_owners)

    def test_incremental_corrupt_source_rejects_without_replay_or_state_changes(self):
        self.fixture()
        self.request('POST', '/api/recipe/remove', {'index': 2})
        before = self.request('GET', '/api/init')['result']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        manifest, grid, owners = self.display_voxels()
        undo, redo = self.worker_history()
        # Seed a valid redo entry to exercise failure preservation even though
        # normal undo clears the session's incremental cache.
        redo.append(copy.deepcopy(undo[-1]))
        history_entries = tuple(map(id, undo)), tuple(map(id, redo))
        original_load = tcad._tcad_snapshot_load_maybe
        foreign_id = tcad.StructureWaferStep(tcad.MaterialDatabase()).step_id

        def damaged_snapshot(ref):
            snapshot = copy.deepcopy(original_load(ref))
            snapshot['display_step_ids'][1] = foreign_id
            return snapshot

        with patch.object(tcad, '_tcad_snapshot_load_maybe', side_effect=damaged_snapshot), \
             patch.object(tcad.StructureWaferStep, 'execute', side_effect=AssertionError('Forbidden replay')) as execute:
            rejected = self.request('POST', '/api/run/to', {'index': 1}, ok=False)
        self.assertEqual(execute.call_count, 0)
        self.assertEqual(rejected['code'], 'restore_failed')
        self.assertIn('identity mapping', rejected['error'])
        self.assertTrue(rejected['rolled_back'])
        undo, redo = self.worker_history()
        self.assertEqual(history_entries, (tuple(map(id, undo)), tuple(map(id, redo))))
        after = self.request('GET', '/api/init')['result']
        for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
        actual_manifest, actual_grid, actual_owners = self.display_voxels()
        self.assertEqual(manifest, actual_manifest)
        np.testing.assert_array_equal(grid, actual_grid)
        np.testing.assert_array_equal(owners, actual_owners)

    def test_incremental_restore_failure_preserves_direct_suffix_and_previous_undo(self):
        self.fixture()
        original = self.request('GET', '/api/init')['result']['recipe']
        _, previous_grid, previous_owners = self.display_voxels()
        self.request('POST', '/api/run/step', {'index': 1})
        self.request('POST', '/api/recipe/remove', {'index': 2})
        before = self.request('GET', '/api/init')['result']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        self.assertTrue(timeline['items'][1]['snapshot_valid'])
        manifest, grid, owners = self.display_voxels()
        original_load = tcad._tcad_snapshot_load_maybe
        foreign_id = tcad.StructureWaferStep(tcad.MaterialDatabase()).step_id

        def damaged_snapshot(ref):
            snapshot = copy.deepcopy(original_load(ref))
            snapshot['display_step_ids'][1] = foreign_id
            return snapshot

        with patch.object(tcad, '_tcad_snapshot_load_maybe', side_effect=damaged_snapshot), \
             patch.object(tcad.StructureWaferStep, 'execute', side_effect=AssertionError('Forbidden replay')) as execute:
            rejected = self.request('POST', '/api/run/to', {'index': 0}, ok=False)
        self.assertEqual(execute.call_count, 0)
        self.assertEqual(rejected['code'], 'restore_failed')
        self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
        after = self.request('GET', '/api/init')['result']
        for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
            self.assertEqual(before[key], after[key], key)
        actual_manifest, actual_grid, actual_owners = self.display_voxels()
        self.assertEqual(manifest, actual_manifest)
        np.testing.assert_array_equal(grid, actual_grid)
        np.testing.assert_array_equal(owners, actual_owners)
        undone = self.request('POST', '/api/undo', {})['result']
        self.assertTrue(undone['undone'])
        self.assertEqual([step['step_id'] for step in original], [step['step_id'] for step in undone['recipe']])
        _, undo_grid, undo_owners = self.display_voxels()
        np.testing.assert_array_equal(previous_grid, undo_grid)
        np.testing.assert_array_equal(previous_owners, undo_owners)
        self.assertTrue(self.request('POST', '/api/redo', {})['result']['redone'])

    def test_incremental_rollback_failure_keeps_recovery_undo_and_refreshes_revision(self):
        self.fixture()
        self.request('POST', '/api/recipe/remove', {'index': 2})
        before = self.request('GET', '/api/init')['result']
        manifest, grid, owners = self.display_voxels()
        undo, _ = self.worker_history()
        history_entries = tuple(map(id, undo))
        original_load = tcad._tcad_snapshot_load_maybe
        original_restore = tcad.ProcessModel.restore_state
        foreign_id = tcad.StructureWaferStep(tcad.MaterialDatabase()).step_id
        restore_calls = 0

        def damaged_snapshot(ref):
            snapshot = copy.deepcopy(original_load(ref))
            snapshot['display_step_ids'][1] = foreign_id
            return snapshot

        def failed_rollback(model, snapshot, **kwargs):
            nonlocal restore_calls
            restore_calls += 1
            if restore_calls == 2:
                raise MemoryError('injected rollback restore failure')
            return original_restore(model, snapshot, **kwargs)

        with patch.object(tcad, '_tcad_snapshot_load_maybe', side_effect=damaged_snapshot), \
             patch.object(tcad.ProcessModel, 'restore_state', autospec=True, side_effect=failed_rollback), \
             patch.object(tcad.StructureWaferStep, 'execute', side_effect=AssertionError('Forbidden replay')) as execute:
            rejected = self.request('POST', '/api/run/to', {'index': 1}, ok=False)
        self.assertEqual(execute.call_count, 0)
        self.assertEqual(restore_calls, 2)
        self.assertEqual(rejected['code'], 'restore_failed')
        self.assertIn('identity mapping', rejected['error'])
        self.assertFalse(rejected['rolled_back'])
        self.assertIn('injected rollback restore failure', rejected['rollback_error'])
        undo, _ = self.worker_history()
        self.assertEqual(len(history_entries) + 1, len(undo))
        self.assertEqual(history_entries, tuple(map(id, undo[:-1])))
        actual_manifest, partial_grid, _ = self.display_voxels()
        self.assertGreater(actual_manifest['revision'], manifest['revision'])
        self.assertEqual(rejected['model_revision'], actual_manifest['revision'])
        self.assertFalse(np.array_equal(grid, partial_grid))
        self.assertEqual(foreign_id, actual_manifest['owner_step_ids']['1'])
        undone = self.request('POST', '/api/undo', {})['result']
        self.assertTrue(undone['undone'])
        self.assertEqual(before['recipe'], undone['recipe'])
        recovered, undo_grid, undo_owners = self.display_voxels()
        np.testing.assert_array_equal(grid, undo_grid)
        np.testing.assert_array_equal(owners, undo_owners)
        self.assertEqual(manifest['owner_step_ids'], recovered['owner_step_ids'])

    def test_incremental_missing_snapshot_still_rebuilds_from_start(self):
        self.fixture()
        original_load = tcad._tcad_snapshot_load_maybe

        def missing_snapshot(ref):
            snapshot = original_load(ref)
            return None if isinstance(snapshot, dict) and 'grid_shape' in snapshot else snapshot

        with patch.object(tcad, '_tcad_snapshot_load_maybe', side_effect=missing_snapshot), \
             patch.object(tcad.StructureWaferStep, 'execute', autospec=True,
                          side_effect=tcad.StructureWaferStep.execute) as execute:
            rebuilt = self.request('POST', '/api/run/to', {'index': 1})
        self.assertTrue(rebuilt['ok'])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.request('GET', '/api/init')['result']['recipe'][1]['runtime_status'], 'done')

    def test_readonly_endpoints_no_execution_revision_or_saved_state_changes(self):
        self.fixture()
        self.request('POST', '/api/recipe/save', {'name': '保存展示'})
        session = next(iter(self.manager.sessions.values()))
        before = self.request('GET', '/api/init')['result']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        formal = self.request('GET', '/api/preview/manifest')['result']
        files = {str(p.relative_to(session.storage_dir)): p.read_bytes()
                 for p in session.storage_dir.rglob('*') if p.is_file() and 'preview' not in str(p.relative_to(session.storage_dir))}
        # Guard actual worker calls after the real recipe has executed.
        with patch.object(tcad.StructureDepositStep, 'execute', side_effect=AssertionError('Unexpected execute')), \
             patch.object(tcad.StructureWaferStep, 'execute', side_effect=AssertionError('Unexpected execute')):
            manifest = self.manifest()
            self.assertTrue(manifest['available'])
            self.assertEqual(manifest['revision'], formal['rev'])
            self.assertEqual(len(manifest['groups']), 3)
            entities = manifest['step_entities']
            self.assertEqual([e['hideable'] for e in entities], [False, True, True, False])
            self.assertEqual(entities[0]['unavailable_reason'], 'initialization')
            for group in manifest['groups']:
                path = '/api/structure/display/mesh?revision={}&owner_id={}&mat_id={}'.format(
                    manifest['revision'], group['owner_id'], group['mat_id'])
                status, headers, raw = self._request(self.manager.url, self.cookie, 'GET', path, None)
                self.assertEqual(status, 200, raw[:500])
                self.assertIn('application/octet-stream', headers.get('content-type', ''))
                self.assertEqual(len(decode_mesh(raw)), group['tri_count'])
                self.assertEqual(raw, self._request(self.manager.url, self.cookie, 'GET', path, None)[2])
            for axis, index in (('X', 3), ('Y', 4), ('Z', 5)):
                section = self.request('GET', '/api/structure/display/slice?revision={}&axis={}&index={}'.format(
                    manifest['revision'], axis, index))['result']
                old = self.request('GET', '/api/slice?axis={}&index={}'.format(axis, index))['result']
                self.assertEqual(section['shape'], old['shape'])
                self.assertEqual(section['material']['data_b64'], old['data_b64'])
                mats = np.frombuffer(base64.b64decode(section['material']['data_b64']), '<u2')
                owners = np.frombuffer(base64.b64decode(section['owner']['data_b64']), '<u4')
                self.assertFalse(owners[mats == 0].any())
            self.assertEqual(manifest, self.manifest())
        after = self.request('GET', '/api/init')['result']
        for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
        self.assertEqual(formal, self.request('GET', '/api/preview/manifest')['result'])
        self.assertEqual(files, {str(p.relative_to(session.storage_dir)): p.read_bytes()
                                for p in session.storage_dir.rglob('*') if p.is_file() and 'preview' not in str(p.relative_to(session.storage_dir))})

    def test_revision_unknown_group_validation_and_wrong_method(self):
        self.fixture()
        manifest = self.manifest()
        rev = manifest['revision']
        for path in ('/api/structure/display/manifest', '/api/structure/display/mesh', '/api/structure/display/slice'):
            self.request('POST', path, {}, expected=404, ok=False)
        for path in ('mesh?owner_id=1&mat_id=1', 'slice?axis=X&index=0'):
            rejected = self.request('GET', '/api/structure/display/{}&revision={}'.format(path, rev + 1), expected=409, ok=False)
            self.assertEqual(rejected['code'], 'revision_mismatch')
        self.request('GET', '/api/structure/display/mesh?revision={}&owner_id=999&mat_id=1'.format(rev), expected=404, ok=False)
        for query in ('revision=bad&owner_id=1&mat_id=1', 'owner_id=1&mat_id=1', 'revision={}&owner_id=-1&mat_id=1'.format(rev)):
            self.request('GET', '/api/structure/display/mesh?' + query, expected=400, ok=False)
        for query in ('axis=Q&index=0', 'axis=X&index=999', 'axis=X&index=bad'):
            self.request('GET', '/api/structure/display/slice?revision={}&{}'.format(rev, query), expected=400, ok=False)
        self.request('POST', '/api/reset', {})
        self.request('GET', '/api/structure/display/mesh?revision={}&owner_id=1&mat_id=1'.format(rev), expected=409, ok=False)

    def test_unknown_legacy_init_is_visible_without_guessed_owner(self):
        manifest = self.manifest()
        self.assertTrue(manifest['available'])
        self.assertTrue(manifest['groups'])
        self.assertTrue(all(g['owner_id'] == 0 and g['step_id'] is None for g in manifest['groups']))
        self.assertIn('unknown_provenance', manifest['unavailable_reasons'])
        self.assertTrue(all(not e['hideable'] for e in manifest['step_entities']))

    def test_preparation_failure_is_cached_explicit_and_never_fake_success(self):
        self.fixture()
        with patch.object(tcad, 'marching_cubes', side_effect=RuntimeError('test extraction failure')) as extraction:
            result = self.manifest()
            self.assertFalse(result['available'])
            self.assertEqual(result['groups'], [])
            self.assertIn('display_preparation_failed', result['unavailable_reasons'])
            self.assertTrue(all(not e['hideable'] for e in result['step_entities']))
            self.assertEqual(result, self.manifest())
            self.assertEqual(extraction.call_count, 1)
            self.request('GET', '/api/structure/display/mesh?revision={}&owner_id=1&mat_id=1'.format(result['revision']), expected=503, ok=False)

    def test_empty_model_and_cookie_sessions_are_isolated(self):
        self.fixture()
        first = self.manifest()
        self.manager.max_users = 2
        self.manager._force_inprocess_worker = True
        _, second_cookie = self.manager.create_session()
        old_cookie = self.cookie
        first_session = next(s for s in self.manager.sessions.values() if s.session_id in old_cookie)
        second_session = next(s for s in self.manager.sessions.values() if s.session_id in second_cookie)
        # Existing compatibility cookies are sticky by client IP; model each
        # client's binding explicitly rather than changing that auth behavior.
        self.manager.bind_client_session('127.0.0.1', second_session.session_id)
        self.cookie = second_cookie
        second = self.manifest()
        self.assertTrue(all(g['owner_id'] == 0 for g in second['groups']))
        self.assertNotEqual(first['owner_step_ids'], second['owner_step_ids'])
        self.request('GET', '/api/structure/display/mesh?revision={}&owner_id=1&mat_id=1'.format(first['revision']), expected=409, ok=False)
        self.request('POST', '/api/recipe/import', {'recipe': {'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 10}},
            {'name': 'Structure Etch', 'params': {'material': 'Silicon', 'depth_nm': 10}},
        ]}})
        self.request('POST', '/api/run/all', {})
        empty = self.manifest()
        self.assertTrue(empty['available'])
        self.assertEqual(empty['groups'], [])
        self.assertTrue(all(not e['hideable'] for e in empty['step_entities']))
        self.cookie = old_cookie
        self.manager.bind_client_session('127.0.0.1', first_session.session_id)
        self.assertEqual(first, self.manifest())
