import copy
import json
import tempfile
import unittest
from unittest.mock import patch
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

    def test_forgetting_a_step_preserves_grid_other_owners_and_unknown_voxels(self):
        self.model.build_substrate('Silicon', 10, emit_log=False)
        removed = self.step('Structure Deposit', material='Silicon', thickness_nm=5)
        retained = self.step('Structure Deposit', material='Silicon', thickness_nm=5)
        source = self.model.display_provenance
        grid, owners = self.model.grid.copy(), source.owners.copy()
        removed_owner, retained_owner = source.owner_for(removed.step_id), source.owner_for(retained.step_id)
        self.assertTrue(source.forget_step(removed.step_id))
        expected = owners.copy()
        expected[owners == removed_owner] = 0
        np.testing.assert_array_equal(grid, self.model.grid)
        np.testing.assert_array_equal(expected, source.owners)
        self.assertEqual(source.step_ids, {retained_owner: retained.step_id})
        self.assertFalse(source.forget_step(removed.step_id))

    def test_forgetting_readonly_source_fails_before_source_changes(self):
        step = self.step('Structure Wafer', thickness_nm=10)
        source = self.model.display_provenance
        owners, identities = source.owners.copy(), dict(source.step_ids)
        source.owners.flags.writeable = False
        with self.assertRaisesRegex(ValueError, 'writable'):
            source.forget_step(step.step_id)
        np.testing.assert_array_equal(owners, source.owners)
        self.assertEqual(identities, source.step_ids)

    def test_forgetting_an_old_unknown_source_keeps_it_unknown(self):
        source = self.model.display_provenance
        grid = self.model.grid.copy()
        self.assertFalse(source.forget_step(tcad.StructureDepositStep(self.db).step_id))
        self.assertIsNone(source.owners)
        self.assertEqual({}, source.step_ids)
        np.testing.assert_array_equal(grid, self.model.grid)

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

    def test_damaged_provenance_restore_preserves_entire_current_model(self):
        self.step('Structure Wafer', thickness_nm=10)
        target = self.model.snapshot_state()
        target['display_owners'] = self.model.display_provenance.owners.copy()
        self.step('Structure Wafer', thickness_nm=20)
        before = self.model.snapshot_state()
        corruptions = {
            'dtype': lambda s: s.update(display_owners=s['display_owners'].astype(np.int32)),
            'shape': lambda s: s.update(display_owners=s['display_owners'][:, :, :-1]),
            'missing_map': lambda s: s.update(display_step_ids={}),
            'invalid_identity': lambda s: s.update(display_step_ids={1: 'broken'}),
            'invalid_payload': lambda s: s.update(display_owners={'codec': 'zlib', 'shape': self.model.grid.shape, 'dtype': 'uint32', 'data': b'broken'}),
        }
        for name, corrupt in corruptions.items():
            with self.subTest(name=name):
                damaged = copy.deepcopy(target)
                corrupt(damaged)
                with self.assertRaises(ValueError):
                    self.model.restore_state(damaged, emit_log=True)
                after = self.model.snapshot_state()
                self.assertEqual(before.keys(), after.keys())
                for key, value in before.items():
                    if isinstance(value, np.ndarray):
                        np.testing.assert_array_equal(value, after[key], err_msg=key)
                    else:
                        self.assertEqual(value, after[key], key)

    def test_direct_provenance_restore_rejection_preserves_current_source(self):
        self.step('Structure Wafer', thickness_nm=10)
        source = self.model.display_provenance
        owners, identities = source.owners, dict(source.step_ids)
        with self.assertRaises(ValueError):
            source.restore(owners.copy(), {}, self.model.grid)
        self.assertIs(owners, source.owners)
        self.assertEqual(identities, source.step_ids)

    def test_owner_payload_metadata_rejected_before_array_allocation(self):
        self.step('Structure Wafer', thickness_nm=10)
        state = self.model.snapshot_state()
        state['grid_compression'] = 'dense'
        state['grid'] = self.model.grid.copy()
        for shape, dtype in (((4, 4, 21), 'uint32'), ((4, 4, 20), 'float64'), ((4, 4, 100000000), 'uint32')):
            with self.subTest(shape=shape, dtype=dtype):
                state['display_owners'] = {'codec': 'zlib', 'shape': shape, 'dtype': dtype, 'data': b'broken'}
                with patch('numpy.empty', side_effect=AssertionError('must validate owner metadata first')) as allocation:
                    with self.assertRaisesRegex(ValueError, 'display owner snapshot'):
                        self.model.restore_state(state)
                    allocation.assert_not_called()

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

    def test_source_bound_identity_collision_is_rejected_without_repair(self):
        from structure_cad.display_provenance import normalize_step_identities
        a = tcad.StructureDepositStep(self.db)
        b = tcad._webui_deserialize_step(tcad._webui_serialize_step(a), self.db)
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            normalize_step_identities([a, b], preserve_ids=True)
        self.assertEqual(a.step_id, b.step_id)


class DisplayStepIdentityRuntimeTests(unittest.TestCase):
    from tests.test_structure_editor_http import StructureEditorHTTPTests as _Harness
    setUp = _Harness.setUp
    _request = _Harness._request
    request = _Harness.request

    def test_damaged_saved_provenance_rejection_preserves_session(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '来源目标', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 20}},
        ]}})
        self.request('POST', '/api/run/all', {})
        saved = self.request('POST', '/api/recipe/save', {'name': '来源目标'})['result']
        self.request('POST', '/api/recipe/new', {'name': '保持当前'})
        session = next(iter(self.manager.sessions.values()))
        entry = next(e for e in saved['recipes'] if e['id'] == saved['id'])
        main = session.storage_dir / 'history' / entry['file']
        target = tcad._webui_pickle_load(main)
        targets = [main] + [p for p in (session.storage_dir / 'history').glob('*autosave*')
                            if tcad._webui_pickle_load(p).get('recipe_id') == saved['id']]
        for damage in ('missing_map', 'foreign_identity'):
            with self.subTest(damage=damage):
                broken = copy.deepcopy(target)
                broken['model_state']['display_step_ids'] = ({} if damage == 'missing_map' else
                    {owner: tcad.StructureWaferStep(tcad.MaterialDatabase()).step_id
                     for owner in target['model_state']['display_step_ids']})
                for path in targets:
                    tcad._webui_pickle_dump(path, broken)
                before = self.request('GET', '/api/init')['result']
                timeline = self.request('POST', '/api/timeline/get', {})['result']
                pointer = json.loads((session.storage_dir / 'session_state.json').read_text())
                rejected = self.request('POST', '/api/recipe/load', {'id': saved['id']}, ok=False)
                self.assertFalse(rejected['ok'])
                after = self.request('GET', '/api/init')['result']
                for key in ('recipe', 'model', 'current_recipe', 'ui_state'):
                    self.assertEqual(before[key], after[key], key)
                self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
                after_pointer = json.loads((session.storage_dir / 'session_state.json').read_text())
                # Existing recipe-switch behavior autosaves the recipe being left;
                # its activity timestamp may advance, but the session must stay bound.
                pointer.pop('last_active_ts', None)
                after_pointer.pop('last_active_ts', None)
                self.assertEqual(pointer, after_pointer)

    def test_damaged_autosave_rejection_preserves_session(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '自动保存来源', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 20}},
        ]}})
        self.request('POST', '/api/run/all', {})
        saved = self.request('POST', '/api/recipe/save', {'name': '自动保存来源'})['result']
        session = next(iter(self.manager.sessions.values()))
        entry = next(e for e in saved['recipes'] if e['id'] == saved['id'])
        target = tcad._webui_pickle_load(session.storage_dir / 'history' / entry['file'])
        self.request('POST', '/api/recipe/new', {'name': '自动保存拒绝后保持'})
        for damage in ('missing_map', 'foreign_identity', 'dtype', 'shape', 'payload'):
            with self.subTest(damage=damage):
                broken = copy.deepcopy(target)
                state = broken['model_state']
                if damage == 'missing_map':
                    state['display_step_ids'] = {}
                elif damage == 'foreign_identity':
                    state['display_step_ids'] = {owner: tcad.StructureWaferStep(tcad.MaterialDatabase()).step_id
                                                for owner in state['display_step_ids']}
                elif damage == 'dtype':
                    state['display_owners'] = np.zeros((12, 12, 32), dtype=np.int32)
                elif damage == 'shape':
                    state['display_owners'] = np.zeros((12, 12, 31), dtype=np.uint32)
                else:
                    state['display_owners']['data'] = b'broken'
                tcad._webui_pickle_dump(session.storage_dir / 'autosave.pkl.gz', broken)
                before = self.request('GET', '/api/init')['result']
                timeline = self.request('POST', '/api/timeline/get', {})['result']
                persisted = (session.storage_dir / 'session_state.json').read_bytes()
                status, _, raw = self._request(self.manager.url, self.cookie, 'POST', '/api/load_autosave', {})
                self.assertEqual(status, 200)
                rejected = json.loads(raw)
                self.assertTrue(not rejected['ok'] or not rejected['result']['loaded'])
                after = self.request('GET', '/api/init')['result']
                for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
                    self.assertEqual(before[key], after[key], key)
                self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
                self.assertEqual(persisted, (session.storage_dir / 'session_state.json').read_bytes())
        tcad._webui_pickle_dump(session.storage_dir / 'autosave.pkl.gz', target)
        restored = self.request('POST', '/api/load_autosave', {})['result']
        self.assertTrue(restored['loaded'])
        current = self.request('GET', '/api/init')['result']['current_recipe']
        self.assertEqual(saved['id'], current['id'])
        self.assertEqual('自动保存来源', current['name'])

    def test_unsupported_source_step_rejected_before_recipe_rebuild_publication(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '完整来源', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 20}},
            {'name': 'Structure Deposit', 'params': {'thickness_nm': 10}},
        ]}})
        self.request('POST', '/api/run/all', {})
        saved = self.request('POST', '/api/recipe/save', {'name': '完整来源'})['result']
        session = next(iter(self.manager.sessions.values()))
        entry = next(e for e in saved['recipes'] if e['id'] == saved['id'])
        main = session.storage_dir / 'history' / entry['file']
        target = tcad._webui_pickle_load(main)
        target['steps_full'][1]['name'] = 'Unsupported Source Step'
        self.request('POST', '/api/recipe/new', {'name': '保持完整会话'})
        targets = [main] + [p for p in (session.storage_dir / 'history').glob('*autosave*')
                            if tcad._webui_pickle_load(p).get('recipe_id') == saved['id']]
        for endpoint, all_skipped in [(endpoint, all_skipped)
                                     for endpoint in ('/api/recipe/load', '/api/load_autosave')
                                     for all_skipped in (False, True)]:
            with self.subTest(endpoint=endpoint, all_skipped=all_skipped):
                fixture = copy.deepcopy(target)
                if all_skipped:
                    fixture['steps_full'][0]['name'] = 'Unsupported Wafer Step'
                for path in targets:
                    tcad._webui_pickle_dump(path, fixture)
                tcad._webui_pickle_dump(session.storage_dir / 'autosave.pkl.gz', fixture)
                original_files = {path: path.read_bytes() for path in targets}
                before = self.request('GET', '/api/init')['result']
                timeline = self.request('POST', '/api/timeline/get', {})['result']
                persisted = json.loads((session.storage_dir / 'session_state.json').read_text())
                body = {'id': saved['id']} if endpoint == '/api/recipe/load' else {}
                status, _, raw = self._request(self.manager.url, self.cookie, 'POST', endpoint, body)
                self.assertEqual(status, 200)
                result = json.loads(raw)
                self.assertTrue(not result['ok'] or result['result'].get('loaded') is False, result)
                after = self.request('GET', '/api/init')['result']
                for key in ('recipe', 'model', 'current_recipe', 'ui_state', 'log'):
                    self.assertEqual(before[key], after[key], key)
                self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
                after_persisted = json.loads((session.storage_dir / 'session_state.json').read_text())
                if endpoint == '/api/recipe/load':
                    persisted.pop('last_active_ts', None)
                    after_persisted.pop('last_active_ts', None)
                self.assertEqual(persisted, after_persisted)
                self.assertEqual(original_files, {path: path.read_bytes() for path in targets})

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

    def test_colliding_import_saved_before_first_response_reloads_stable_ids(self):
        step = tcad.StructureDepositStep(tcad.MaterialDatabase())
        blob = tcad._webui_serialize_step(step)
        imported = self.request('POST', '/api/recipe/import', {'recipe': {'name': '重复身份落盘', 'steps_full': [blob, blob]}})['result']
        identities = [s['step_id'] for s in imported['recipe']]
        recipe_id = imported['current_recipe']['id']
        session = next(iter(self.manager.sessions.values()))
        entry = next(entry for entry in imported['recipes'] if entry['id'] == recipe_id)
        stored = tcad._webui_pickle_load(session.storage_dir / 'history' / entry['file'])
        self.assertEqual(identities, [s['step_id'] for s in stored['steps_full']])
        self.request('POST', '/api/recipe/new', {'name': '切换配方'})
        loaded = self.request('POST', '/api/recipe/load', {'id': recipe_id})['result']
        self.assertEqual(identities, [s['step_id'] for s in loaded['recipe']])

    def test_library_colliding_import_persists_normalized_ids_before_response(self):
        self.request('GET', '/api/init')
        session = next(iter(self.manager.sessions.values()))
        profile = session.rpc('profile_set', {'department': '来源测试', 'name': '测试', 'employee_id': '001'})
        self.assertTrue(profile['ok'], profile)
        step = tcad.StructureDepositStep(tcad.MaterialDatabase())
        blob = tcad._webui_serialize_step(step)
        item = tcad._library_store_blob(Path(self.directory.name), session_id=session.session_id,
                                       dept='来源测试', kind='recipes', title='重复来源', cat1='测试', cat2='',
                                       blob={'name': '重复来源', 'steps_full': [blob, blob]})
        imported = self.request('POST', '/api/library/recipes/import', {'id': item['id']})['result']
        identities = [s['step_id'] for s in imported['recipe']]
        self.assertEqual(len(set(identities)), 2)
        init = self.request('GET', '/api/init')['result']
        recipe_id = init['current_recipe']['id']
        entry = next(entry for entry in init['recipes'] if entry['id'] == recipe_id)
        stored = tcad._webui_pickle_load(session.storage_dir / 'history' / entry['file'])
        self.assertEqual(identities, [s['step_id'] for s in stored['steps_full']])
        self.request('POST', '/api/recipe/new', {'name': '再次切换'})
        loaded = self.request('POST', '/api/recipe/load', {'id': recipe_id})['result']
        self.assertEqual(identities, [s['step_id'] for s in loaded['recipe']])

    def test_source_bound_corrupt_saved_ids_fail_before_model_or_recipe_restore(self):
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '有来源', 'steps_full': [
            {'name': 'Structure Wafer', 'params': {'thickness_nm': 20}},
            {'name': 'Structure Deposit', 'params': {'thickness_nm': 10}},
        ]}})
        self.request('POST', '/api/run/all', {})
        saved = self.request('POST', '/api/recipe/save', {'name': '有来源'})['result']
        recipe_id = saved['id']
        self.request('POST', '/api/recipe/new', {'name': '当前配方'})
        session = next(iter(self.manager.sessions.values()))
        entry = next(entry for entry in saved['recipes'] if entry['id'] == recipe_id)
        main_path = session.storage_dir / 'history' / entry['file']
        snapshot = tcad._webui_pickle_load(main_path)
        self.assertIsNotNone(snapshot['model_state']['display_owners'])
        snapshot['steps_full'][1]['step_id'] = snapshot['steps_full'][0]['step_id']
        tcad._webui_pickle_dump(main_path, snapshot)
        # Load chooses the latest autosave; inject the same corrupt fixture there.
        for path in (session.storage_dir / 'history').glob('*autosave*'):
            blob = tcad._webui_pickle_load(path)
            if blob.get('recipe_id') == recipe_id:
                tcad._webui_pickle_dump(path, snapshot)
        before = self.request('GET', '/api/init')['result']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        rejected = self.request('POST', '/api/recipe/load', {'id': recipe_id}, ok=False)
        self.assertIn('source-bound', rejected['error'])
        after = self.request('GET', '/api/init')['result']
        self.assertEqual(before['recipe'], after['recipe'])
        self.assertEqual(before['model'], after['model'])
        self.assertEqual(before['current_recipe'], after['current_recipe'])
        self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])

    def test_old_unknown_source_load_repairs_and_persists_colliding_ids(self):
        blob = tcad._webui_serialize_step(tcad.StructureDepositStep(tcad.MaterialDatabase()))
        imported = self.request('POST', '/api/recipe/import', {'recipe': {'name': '旧未知来源', 'steps_full': [blob, blob]}})['result']
        recipe_id = imported['current_recipe']['id']
        self.request('POST', '/api/recipe/new', {'name': '当前'})
        session = next(iter(self.manager.sessions.values()))
        entry = next(entry for entry in imported['recipes'] if entry['id'] == recipe_id)
        main_path = session.storage_dir / 'history' / entry['file']
        old = tcad._webui_pickle_load(main_path)
        old['steps_full'][1]['step_id'] = old['steps_full'][0]['step_id']
        old['model_state'].pop('display_owners', None)
        old['model_state'].pop('display_step_ids', None)
        tcad._webui_pickle_dump(main_path, old)
        targets = [main_path]
        for path in (session.storage_dir / 'history').glob('*autosave*'):
            if tcad._webui_pickle_load(path).get('recipe_id') == recipe_id:
                tcad._webui_pickle_dump(path, old)
                targets.append(path)
        loaded = self.request('POST', '/api/recipe/load', {'id': recipe_id})['result']
        identities = [s['step_id'] for s in loaded['recipe']]
        self.assertEqual(identities[0], blob['step_id'])
        self.assertEqual(len(set(identities)), 2)
        # The selected file is rewritten on this explicit load, not on /api/init.
        self.assertTrue(any([s['step_id'] for s in tcad._webui_pickle_load(path)['steps_full']] == identities for path in targets))
        self.request('GET', '/api/init')
        self.request('POST', '/api/recipe/new', {'name': '切换'})
        reloaded = self.request('POST', '/api/recipe/load', {'id': recipe_id})['result']
        self.assertEqual(identities, [s['step_id'] for s in reloaded['recipe']])

    def test_library_upload_import_preserves_valid_step_identity(self):
        steps = self.request('POST', '/api/recipe/add', {'name': 'Structure Deposit'})['result']
        identities = [step['step_id'] for step in steps]
        session = next(iter(self.manager.sessions.values()))
        self.assertTrue(session.rpc('profile_set', {'department': '来源测试', 'name': '测试', 'employee_id': '001'})['ok'])
        uploaded = self.request('POST', '/api/library/recipes/upload', {'title': '合法来源', 'department': '来源测试'})['result']
        loaded = self.request('POST', '/api/library/recipes/import', {'id': uploaded['item']['id']})['result']
        self.assertEqual(identities, [step['step_id'] for step in loaded['recipe']])

    def test_legacy_last_active_autosave_repairs_are_persisted_for_next_restore(self):
        blob = tcad._webui_serialize_step(tcad.StructureDepositStep(tcad.MaterialDatabase()))
        imported = self.request('POST', '/api/recipe/import', {'recipe': {'name': '旧自动保存', 'steps_full': [blob, blob]}})['result']
        session = next(iter(self.manager.sessions.values()))
        entry = next(entry for entry in imported['recipes'] if entry['id'] == imported['current_recipe']['id'])
        old = tcad._webui_pickle_load(session.storage_dir / 'history' / entry['file'])
        old['steps_full'][1]['step_id'] = old['steps_full'][0]['step_id']
        old['model_state'].pop('display_owners', None)
        old['model_state'].pop('display_step_ids', None)
        pointer = session.storage_dir / 'autosave.pkl.gz'
        tcad._webui_pickle_dump(pointer, old)
        first = self.request('POST', '/api/load_autosave', {})['result']
        self.assertTrue(first['loaded'])
        identities = [step['step_id'] for step in self.request('GET', '/api/init')['result']['recipe']]
        self.assertEqual(len(set(identities)), 2)
        self.assertEqual(identities, [step['step_id'] for step in tcad._webui_pickle_load(pointer)['steps_full']])
        second = self.request('POST', '/api/load_autosave', {})['result']
        self.assertTrue(second['loaded'])
        self.assertEqual(identities, [step['step_id'] for step in self.request('GET', '/api/init')['result']['recipe']])
