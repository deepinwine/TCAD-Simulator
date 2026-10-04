import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore
from tests.test_mask_assets import _candidate, _Adapter


class MaskAssetSecurityTests(unittest.TestCase):
    def test_http_rejects_body_lengths_and_non_decimal_revisions(self):
        import http.client
        import json
        from urllib.parse import urlparse
        from tests.test_webui_cad_shell import M2ApiContractTests
        with tempfile.TemporaryDirectory() as tmp:
            helper = M2ApiContractTests()
            manager = helper._start_manager(tmp)
            try:
                _session, cookie = manager.create_session()
                base = urlparse(manager.url)
                for length, expected in (('-1', 400), ('bad', 400), ('67108865', 413)):
                    connection = http.client.HTTPConnection(base.hostname, base.port, timeout=10)
                    connection.request('POST', '/api/mask/asset/save', body=b'', headers={
                        'Cookie': cookie.split(';', 1)[0], 'Content-Length': length,
                        'Content-Type': 'application/json',
                    })
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, expected)
                    self.assertFalse(payload['ok'])
                    self.assertIn('code', payload)
                    self.assertIn('params', payload)
                    connection.close()
                for revision in ('1.1', '%2B1', '%201', 'True'):
                    status, _headers, raw = helper._request(manager.url, cookie, 'GET',
                        '/api/mask/asset?id=mask_metal1&revision=' + revision)
                    self.assertEqual(status, 400, raw)
                    self.assertEqual(json.loads(raw)['code'], 'invalid_mask_asset_reference')
            finally:
                manager.stop()

    def test_preview_preserves_budget_error_status(self):
        import json
        import tcad_simulator as tcad
        from tests.test_webui_cad_shell import M2ApiContractTests
        with tempfile.TemporaryDirectory() as tmp:
            helper = M2ApiContractTests()
            manager = helper._start_manager(tmp)
            try:
                _session, cookie = manager.create_session()
                helper._request(manager.url, cookie, 'POST', '/api/recipe/new', {'name': 'Security'})
                _status, _headers, raw = helper._request(manager.url, cookie, 'POST', '/api/recipe/insert_steps',
                                                       {'steps': [{'name': 'Mask Exposure'}]})
                index = len(json.loads(raw)['result']) - 1
                status, _headers, raw = helper._request(manager.url, cookie, 'POST', '/api/mask/asset/save',
                                                       {'asset': _candidate(), 'step_index': index})
                self.assertEqual(status, 200, raw)
                error = MaskAssetError('mask_asset_budget_exceeded', 'Geometry exceeds budget', status=413)
                with mock.patch.object(tcad.WebUISession, 'rpc', return_value={**error.envelope(), 'status': 413}):
                    status, _headers, raw = helper._request(manager.url, cookie, 'GET',
                                                           f'/api/mask/preview_step?step_index={index}')
                self.assertEqual(status, 413, raw)
                self.assertEqual(json.loads(raw)['code'], 'mask_asset_budget_exceeded')
            finally:
                manager.stop()

    def test_legacy_mask_file_executes(self):
        import numpy as np
        from PIL import Image
        from tcad_simulator import ExposureStep, MaterialDatabase
        from tests.test_mask_assets import MaskAssetExposureTests
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'legacy.png'
            Image.fromarray(np.full((10, 20), 255, dtype=np.uint8)).save(path)
            step = ExposureStep(MaterialDatabase())
            step.params.update(mask_mode='Image', mask_file=str(path))
            model = MaskAssetExposureTests._Model()
            step.execute(model)
            self.assertEqual(len(model.calls), 1)
            self.assertTrue(model.calls[0][1]['mask_override'].all())

    def test_http_mask_json_preflights_length_before_reading(self):
        import tcad_simulator as tcad
        for length, status in (('-1', 400), ('abc', 400), ('67108865', 413), ('9' * 5000, 413)):
            with self.subTest(length=length):
                handler = object.__new__(tcad._WebUIRequestHandler)
                handler.headers = {'Content-Length': length}
                handler.rfile = mock.Mock()
                with self.assertRaises(MaskAssetError) as caught:
                    handler._read_mask_json()
                self.assertEqual(caught.exception.status, status)
                handler.rfile.read.assert_not_called()

    def test_http_rpc_transport_errors_have_safe_envelopes(self):
        import tcad_simulator as tcad
        handler = object.__new__(tcad._WebUIRequestHandler)
        session = mock.Mock()
        session.rpc.return_value = {'ok': False, 'error': '/private/session/worker.log: crashed'}
        result = handler._mask_rpc(session, 'mask_asset_get', {})
        self.assertEqual(result['code'], 'mask_asset_apply_failed')
        self.assertEqual(result['params'], {})
        self.assertEqual(result['status'], 500)
        self.assertNotIn('/private', str(result))
        session.rpc.side_effect = OSError('/private/session')
        result = handler._mask_rpc(session, 'mask_asset_get', {'format': 'gds'})
        self.assertEqual(result['code'], 'mask_asset_export_failed')
        self.assertNotIn('/private', str(result))

    def test_rpc_exact_revision_error_envelopes(self):
        import tcad_simulator as tcad
        from tests.test_mask_asset_transaction import WorkerConnection, DOMAIN
        with tempfile.TemporaryDirectory() as tmp:
            conn = WorkerConnection([('mask_asset_get', {'id': 'mask_metal1', 'revision': revision})
                                     for revision in (True, 1.1, '1')])
            tcad._webui_worker_main(conn, tmp, DOMAIN)
            for response in conn.responses:
                self.assertEqual(response.get('code'), 'invalid_mask_asset_reference')
                self.assertEqual(response.get('status'), 400)

    def test_exposure_requires_exact_revision(self):
        from tcad_simulator import ExposureStep, MaterialDatabase
        step = ExposureStep(MaterialDatabase())
        step.params.update(mask_mode='Asset', mask_asset_id='mask_metal1')
        for value in (True, 1.1, '1'):
            step.params['mask_asset_revision'] = value
            with self.subTest(value=value), self.assertRaises(MaskAssetError) as caught:
                step.execute(mock.Mock())
            self.assertEqual(caught.exception.code, 'invalid_mask_asset_reference')

    def test_asset_preview_reads_saved_exact_revision(self):
        import tcad_simulator as tcad
        from tests.test_mask_asset_transaction import WorkerConnection, DOMAIN
        with tempfile.TemporaryDirectory() as tmp:
            conn = WorkerConnection([
                ('recipe_insert_steps', {'steps': [{'name': 'Mask Exposure'}], 'insert_index': -1}),
                ('mask_asset_save_apply', {'step_index': 0, 'asset': _candidate()}),
                ('mask_preview_step', {'step_index': 0}),
            ])
            with mock.patch.object(MaskAssetService, 'rasterize', wraps=None,
                                   return_value=(__import__('numpy').zeros((8, 8), dtype=bool), mock.Mock())) as raster:
                tcad._webui_worker_main(conn, tmp, DOMAIN)
            self.assertTrue(conn.responses[-1]['ok'], conn.responses[-1])
            raster.assert_called_once_with('mask_metal1', 1, shape=(192, 192), bounds=(0.0, 0.0, 960.0, 960.0))

    def test_store_rejects_symlinks_without_touching_external_bytes(self):
        for component in ('mask_assets', 'mask_assets/mask_metal1',
                          'mask_assets/mask_metal1/revisions',
                          'mask_assets/mask_metal1/manifest.json',
                          'mask_assets/mask_metal1/revisions/1.json'):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'session'
                root.mkdir()
                external = Path(tmp) / 'external'
                external.mkdir()
                marker = external / 'marker'
                marker.write_bytes(b'UNCHANGED')
                target = root / component
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(marker if target.suffix else external)
                store = MaskAssetStore(root)
                service = MaskAssetService(store, adapter=_Adapter())
                for action in (lambda: service.save_candidate(_candidate()),
                               lambda: store.get('mask_metal1', 1),
                               lambda: store.delete('mask_metal1')):
                    with self.assertRaises(MaskAssetError):
                        action()
                self.assertEqual(marker.read_bytes(), b'UNCHANGED')

    def test_exact_revision_rejects_coercion(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MaskAssetService(MaskAssetStore(Path(tmp)), adapter=_Adapter())
            service.save_candidate(_candidate())
            for revision in (True, 1.1, 1.0, '1', 0, -1):
                with self.subTest(revision=revision), self.assertRaises(MaskAssetError) as caught:
                    service.get('mask_metal1', revision)
                self.assertEqual(caught.exception.code, 'invalid_mask_asset_reference')

    def test_third_party_import_and_export_errors_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = _Adapter()
            service = MaskAssetService(MaskAssetStore(Path(tmp)), adapter=adapter)
            service.save_candidate(_candidate())
            for operation, method, code in (
                (lambda: service.import_gds(Path('/private/secret.gds'), asset_id='x', name='x'), 'read', 'invalid_mask_asset_import'),
                (lambda: service.export_gds('mask_metal1', 1, Path(tmp) / 'x.gds'), 'write', 'mask_asset_export_failed'),
            ):
                with mock.patch.object(adapter, method, side_effect=OSError('/private/secret')):
                    with self.assertRaises(MaskAssetError) as caught:
                        operation()
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('/private', str(caught.exception.envelope()))
