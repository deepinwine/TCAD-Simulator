import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore
from tests.test_mask_assets import _candidate, _Adapter


class MaskAssetSecurityTests(unittest.TestCase):
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
