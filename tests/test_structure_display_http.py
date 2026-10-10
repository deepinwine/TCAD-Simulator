"""Additive display endpoints preserve formal execution and persistence."""
import base64
import json
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
