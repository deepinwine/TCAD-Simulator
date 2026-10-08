"""Configured step creation is a single validated HTTP transaction."""
import json
import tempfile
import unittest
import struct
import numpy as np
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

    def test_atomic_type_replacement_uses_new_defaults_preserves_metadata(self):
        steps = self.request('POST', '/api/recipe/add', {'name':'Structure Deposit', 'params':{'thickness_nm':35}, 'instance_name':'可编辑层'})['result']
        index = len(steps)-1
        self.request('POST', '/api/step/set', {'index':index, 'enabled':False, 'group':'工艺组', 'loop':'L'})
        result = self.request('POST', '/api/step/set', {'index':index, 'name':'Structure Etch'})['result']
        self.assertEqual(result['name'], 'Structure Etch')
        self.assertEqual(result['instance_name'], '可编辑层')
        self.assertFalse(result['enabled'])
        self.assertEqual(result['group'], '工艺组')
        self.assertEqual(result['loop'], 'L')
        self.assertNotIn('thickness_nm', result['params'])
        self.assertEqual(result['params']['depth_nm'], 100)
        old = self.request('POST', '/api/step/set', {'index':index, 'params':{'depth_nm':10}})['result']
        self.assertEqual(old['params']['depth_nm'],10)

    def test_invalid_replacement_is_atomic_and_configuration_does_not_execute(self):
        steps = self.request('POST', '/api/recipe/add', {'name':'Structure Deposit'})['result']
        index = len(steps)-1
        timeline = self.request('POST', '/api/timeline/get', {})['result']
        for payload in ({'name':'Bogus'}, {'name':'Structure Etch','params':{'thickness_nm':35}},
                        {'name':'Structure Deposit','params':{'thickness_nm':1e300}},
                        {'name':'Structure Doping','params':{'depth_nm':.1}},
                        {'name':'Structure Pattern','params':{'mask_mode':'Asset','mask_asset_id':'missing','mask_asset_revision':1}}):
            with self.subTest(payload=payload):
                self.request('POST', '/api/step/set', {'index':index,'enabled':False,**payload},ok=False)
                self.assertEqual(steps,self.request('GET','/api/init')['result']['recipe'])
                self.assertEqual(timeline,self.request('POST','/api/timeline/get',{})['result'])
        # A step can be configured before the material required by execution exists.
        result = self.request('POST','/api/step/set',{'index':index,'name':'Structure Epitaxy','params':{'material':'Germanium','seed_material':'Germanium','thickness_nm':10}})['result']
        self.assertEqual(result['name'],'Structure Epitaxy')

    def test_doping_real_field_pointcloud_timeline_and_undo(self):
        self.request('POST','/api/recipe/import',{'recipe':{'steps_full':[
            {'name':'Structure Wafer','params':{'material':'Silicon','thickness_nm':40}},
            {'name':'Structure Doping','params':{'material':'Silicon','species':'B','concentration_cm3':1e19,'depth_nm':10,'coverage':'Full wafer'}}]}})
        self.request('POST','/api/run/step',{'index':0})
        before = self.request('GET','/api/preview/manifest')['result']['meshes']
        self.request('POST','/api/run/step',{'index':1})
        self.assertEqual({m['mat_id'] for m in before},{m['mat_id'] for m in self.request('GET','/api/preview/manifest')['result']['meshes']})
        status, headers, raw = self._request(self.manager.url,self.cookie,'GET','/api/preview/elements?channels=dopant&quality=high&max_points=1000',None)
        self.assertEqual(status,200)
        magic, version, flags, count, size = struct.unpack('<8sIIII',raw[:24])
        self.assertEqual(magic,b'TCADPNT0')
        self.assertGreater(count,0)
        meta = json.loads(raw[24:24+size])
        self.assertTrue(any(c['name']=='Dopant(B)' for c in meta['channels']))
        offset = 24 + size + (-size)%4
        positions = np.frombuffer(raw,dtype='<f4',count=count*3,offset=offset)
        self.assertTrue(np.isfinite(positions).all())
        self.request('POST','/api/undo',{})
        self.request('POST','/api/redo',{})
        status, _, restored = self._request(self.manager.url,self.cookie,'GET','/api/preview/elements?channels=dopant&quality=high&max_points=1000',None)
        self.assertGreater(struct.unpack('<8sIIII',restored[:24])[3],0)

    def test_project_settings_export_import_preserves_steps_and_rejects_invalid_domain(self):
        self.request('POST','/api/recipe/import',{'recipe':{'name':'项目设置配方','steps_full':[
            {'name':'Structure Wafer','instance_name':'基础晶圆','params':{'material':'Silicon','thickness_nm':40}},
            {'name':'Structure Deposit','instance_name':'氧化层','group':'绝缘','loop':'A','params':{'material':'Silicon Dioxide','thickness_nm':10}}]}})
        self.request('POST','/api/run/all',{})
        status, _, raw = self._request(self.manager.url,self.cookie,'GET','/api/recipe/export?scope=current',None)
        exported = json.loads(raw)
        self.assertEqual(status,200)
        exported['domain'] = {'grid_shape':[14,10,24],'voxel_size_nm':5,'threads':1}
        for key in ('params','params_raw'):
            exported['steps_full'][0][key].update(material='Polysilicon',thickness_nm=30)
        self.request('POST','/api/recipe/import',{'recipe':exported})
        init = self.request('GET','/api/init')['result']
        self.assertEqual(init['recipe'][1]['instance_name'],'氧化层')
        self.assertEqual(init['recipe'][1]['group'],'绝缘')
        self.assertEqual(init['recipe'][1]['loop'],'A')
        self.assertEqual(init['model']['grid_shape'],[14,10,24])
        self.request('POST','/api/run/all',{})
        before = self.request('GET','/api/init')['result']['recipe']
        timeline = self.request('POST','/api/timeline/get',{})['result']
        exported['domain']['grid_shape'][2] = 2
        self.request('POST','/api/recipe/import',{'recipe':exported},ok=False)
        self.assertEqual(before,self.request('GET','/api/init')['result']['recipe'])
        self.assertEqual(timeline,self.request('POST','/api/timeline/get',{})['result'])

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
