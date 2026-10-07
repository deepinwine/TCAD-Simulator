"""Structure geometry through the real HTTP session and immutable asset bridge."""
import copy
import json
import io
import tempfile
import unittest
from pathlib import Path
import tcad_simulator as tcad
import numpy as np
from PIL import Image
from tests import test_webui_cad_shell as shell_tests


class StructureHTTPTests(unittest.TestCase):
    _request = shell_tests.M2ApiContractTests._request

    def request(self, method, path, body=None, expected=200):
        status, _, raw = self._request(self.base, self.cookie, method, path, body)
        self.assertEqual(status, expected, raw[:1000])
        result = json.loads(raw)
        self.assertEqual(result['ok'], expected == 200, result)
        return result

    def test_demo_build_export_assets_and_atomic_invalid_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = tcad.WebUIServerManager(host='127.0.0.1', port=0, max_users=1,
                storage_root=Path(directory), enable_ai_agent=False,
                default_domain={'grid_shape':[16,16,32], 'voxel_size_nm':5, 'threads':1})
            manager.start()
            try:
                _, self.cookie = manager.create_session()
                self.base = manager.url
                flow = self.request('GET', '/api/init')['result']['demo_recipes']['Structure CAD — Trench']
                self.request('POST', '/api/recipe/import', {'recipe':flow})
                status, _, png = self._request(self.base,self.cookie,'GET','/api/mask/preview_step?step_index=2')
                self.assertEqual(status,200)
                preview = np.asarray(Image.open(io.BytesIO(png)))[:,:,0] >= 128
                probe = tcad.ProcessModel(tcad.MaterialDatabase(),grid_shape=(64,64,64),voxel_size_nm=5,max_workers=1)
                try:
                    step = tcad._webui_deserialize_step(flow['steps'][2],probe.material_db)
                    np.testing.assert_array_equal(preview,step.geometry_mask(probe))
                finally:
                    probe.parallel.shutdown()
                self.request('POST', '/api/run/all', {})
                manifest = self.request('GET', '/api/preview/manifest?mode=solid')['result']
                db = tcad.MaterialDatabase()
                self.assertEqual({int(m['mat_id']) for m in manifest['meshes']}, {db.id_for(n) for n in ('Silicon','Silicon Dioxide','Copper')})
                for mesh in manifest['meshes']:
                    status, _, stl = self._request(self.base, self.cookie, 'GET', f'/api/preview/stl?mat_id={mesh["mat_id"]}&rev={manifest["rev"]}&mode=solid')
                    self.assertEqual(status, 200)
                    self.assertGreater(len(stl), 84)
                asset = {'version':1, 'id':'cad_mask', 'name':'CAD opening', 'coordinate_unit':'nm',
                    'bounds_nm':[0,0,320,320], 'layers':[{'id':'1/0','layer':1,'datatype':0,'name':'M1','visible':True}],
                    'shapes':[{'id':'left','type':'rectangle','layer_id':'1/0','x_nm':0,'y_nm':0,'width_nm':160,'height_nm':320}], 'source':{'kind':'editor'}}
                saved = self.request('POST','/api/mask/asset/save', {'asset':asset,'step_index':2})['result']
                self.assertEqual(saved['step']['name'], 'Structure Pattern')
                self.assertEqual(saved['step']['params']['mask_asset_revision'],saved['asset']['revision'])
                self.request('POST','/api/run/all', {})
                revision = self.request('GET', '/api/mask/asset?id=cad_mask&revision=1')['result']
                self.assertEqual(revision['sha256'],saved['asset']['sha256'])
                before = self.request('GET','/api/init')['result']['recipe']
                assets = self.request('GET','/api/mask/assets')['result']
                bad = copy.deepcopy(asset)
                bad['shapes'][0]['width_nm'] = -1
                self.request('POST','/api/mask/asset/save', {'asset':bad,'step_index':2}, expected=400)
                self.assertEqual(before,self.request('GET','/api/init')['result']['recipe'])
                self.assertEqual(assets,self.request('GET','/api/mask/assets')['result'])
                def geometry_bytes():
                    current = self.request('GET','/api/preview/manifest?mode=solid')['result']
                    geometry = {}
                    for mesh in current['meshes']:
                        status, _, data = self._request(self.base,self.cookie,'GET',f'/api/preview/stl?mat_id={mesh["mat_id"]}&rev={current["rev"]}&mode=solid')
                        self.assertEqual(status,200)
                        geometry[mesh['mat_id']] = data
                    return geometry
                geometry = geometry_bytes()
                self.request('POST','/api/undo', {})
                self.request('POST','/api/redo', {})
                self.assertEqual(geometry_bytes(),geometry)
            finally:
                manager.stop()
