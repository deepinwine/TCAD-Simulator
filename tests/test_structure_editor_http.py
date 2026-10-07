"""Configured step creation is a single validated HTTP transaction."""
import json
import tempfile
import unittest
from pathlib import Path

import tcad_simulator as tcad
from tests import test_webui_cad_shell as shell_tests


class StructureEditorHTTPTests(unittest.TestCase):
    _request = shell_tests.M2ApiContractTests._request

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.manager = tcad.WebUIServerManager(
            host='127.0.0.1', port=0, max_users=1,
            storage_root=Path(self.directory.name), enable_ai_agent=False,
            default_domain={'grid_shape': [12, 12, 32], 'voxel_size_nm': 5, 'threads': 1},
        )
        self.manager.start()
        self.addCleanup(self.manager.stop)
        _, self.cookie = self.manager.create_session()

    def request(self, method, path, body=None, expected=200, ok=True):
        status, _, raw = self._request(
            self.manager.url, self.cookie, method, path, body,
        )
        self.assertEqual(status, expected, raw[:1000])
        result = json.loads(raw)
        self.assertEqual(result['ok'], ok, result)
        return result

    def test_templates_match_executable_factories_without_changing_recipe(self):
        init = self.request('GET', '/api/init')['result']
        templates = init['factory_templates']
        self.assertEqual({step['name'] for step in templates}, set(init['recipe_factories']))
        pattern = next(step for step in templates if step['name'] == 'Structure Pattern')
        self.assertEqual(pattern['params']['mask_mode'], 'Procedural')
        deposit = next(step for step in templates if step['name'] == 'Structure Deposit')
        self.assertIn('thickness_nm', {spec['key'] for spec in deposit['parameter_specs']})
        self.assertEqual(init['recipe'], self.request('GET', '/api/init')['result']['recipe'])

    def test_configured_add_keeps_values_name_and_legacy_name_only(self):
        before = self.request('GET', '/api/init')['result']['recipe']
        steps = self.request('POST', '/api/recipe/add', {
            'name': 'Structure Deposit', 'params': {'material': 'Copper', 'thickness_nm': 35},
            'instance_name': '铜互连层',
        })['result']
        self.assertEqual(len(steps), len(before) + 1)
        self.assertEqual(steps[-1]['instance_name'], '铜互连层')
        self.assertEqual(steps[-1]['params']['thickness_nm'], 35)
        self.assertEqual(steps[-1]['params']['material'], tcad.MaterialDatabase().id_for('Copper'))
        legacy = self.request('POST', '/api/recipe/add', {'name': 'Structure Deposit'})['result']
        self.assertEqual(len(legacy), len(steps) + 1)
        self.assertEqual(legacy[-1]['params']['thickness_nm'],
                         tcad.StructureDepositStep(tcad.MaterialDatabase()).params['thickness_nm'])

    def test_invalid_candidates_leave_recipe_and_timeline_unchanged(self):
        before = self.request('GET', '/api/init')['result']['recipe']
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        bad_params = [[], {'thickness_nm': -1}, {'thickness_nm': True},
                      {'thickness_nm': 0}, {'thickness_nm': 1}, {'thickness_nm': 1e300},
                      {'material': True},
                      {'material': 'unregistered'}, {'unknown_parameter': 1}]
        for params in bad_params:
            with self.subTest(params=params):
                self.request('POST', '/api/recipe/add', {
                    'name': 'Structure Deposit', 'params': params,
                }, ok=False)
                self.assertEqual(before, self.request('GET', '/api/init')['result']['recipe'])
                self.assertEqual(timeline, self.request('POST', '/api/timeline/get', {})['result'])
        for label in (123, '', ' ' * 2, 'x' * 81):
            with self.subTest(label=label):
                self.request('POST', '/api/recipe/add', {
                    'name': 'Structure Deposit', 'instance_name': label,
                }, ok=False)
                self.assertEqual(before, self.request('GET', '/api/init')['result']['recipe'])

    def test_configured_pattern_retains_procedural_and_checks_coupled_dimensions(self):
        steps = self.request('POST', '/api/recipe/add', {
            'name': 'Structure Pattern',
            'params': {'mask_mode': 'Procedural', 'pattern': 'Lines',
                       'critical_dimension': 10, 'pitch': 20},
        })['result']
        self.assertEqual(steps[-1]['params']['mask_mode'], 'Procedural')
        for cd, pitch in ((50, 10), (1, 1)):
            self.request('POST', '/api/recipe/add', {
                'name': 'Structure Pattern', 'params': {
                    'mask_mode': 'Procedural', 'pattern': 'Lines',
                    'critical_dimension': cd, 'pitch': pitch,
                },
            }, ok=False)
            self.assertEqual(steps, self.request('GET', '/api/init')['result']['recipe'])
