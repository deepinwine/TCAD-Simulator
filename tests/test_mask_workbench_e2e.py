"""Real HTTP mask-to-geometry regression, using existing RPC slices for diagnostics."""
import base64
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import tcad_simulator as tcad
from tests import test_webui_cad_shell as shell_tests


class MaskWorkbenchEndToEndTests(unittest.TestCase):
    _request = shell_tests.M2ApiContractTests._request

    def request_json(self, method, path, body=None, expected=200, **kwargs):
        status, _, raw = self._request(self.base, self.cookie, method, path, body, **kwargs)
        self.assertEqual(status, expected, raw[:1000])
        payload = json.loads(raw)
        self.assertEqual(payload.get("ok"), expected == 200, payload)
        return payload

    def counts(self):
        halves = [np.zeros(256, dtype=np.int64), np.zeros(256, dtype=np.int64)]
        for x in range(32):
            response = self.session.rpc("slice", {"axis": "X", "index": x}, timeout_s=30)
            self.assertTrue(response["ok"], response)
            section = np.frombuffer(base64.b64decode(response["result"]["data_b64"]), dtype=np.uint16)
            counts = np.bincount(section, minlength=256)
            halves[x // 16] += counts[:256]
        return tuple(tuple(map(int, half)) for half in halves)

    @staticmethod
    def multipart(filename, data):
        return ((f'--mask-e2e\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n').encode()
                + data + b"\r\n--mask-e2e--\r\n")

    def exercise(self, missing_gdstk=False):
        with tempfile.TemporaryDirectory() as directory:
            manager = tcad.WebUIServerManager(
                host="127.0.0.1", port=0, max_users=1, storage_root=Path(directory),
                enable_ai_agent=False,
                default_domain={"grid_shape": [32, 32, 32], "voxel_size_nm": 5.0, "threads": 1},
            )
            # Keep the worker under the same sys.modules patch as the HTTP service.
            if missing_gdstk:
                manager._force_inprocess_worker = True
            manager.start()
            try:
                self.session, self.cookie = manager.create_session()
                self.base = manager.url
                self.request_json("POST", "/api/recipe/new", {"name": "Half-plane lithography"})
                self.request_json("POST", "/api/recipe/insert_steps", {"steps": [
                    {"name": name} for name in ["Spin Resist", "Mask Exposure", "Resist Develop", "Etch"]
                ]})
                for index, params in enumerate([
                    {"thickness_nm": 60}, {"thickness_nm": 30},
                    {"advanced_enable": True, "dose": 100, "opc_enable": False},
                    {"time": 2},
                    {"material": "Silicon", "target_depth_nm": 20, "nominal_rate_nm_s": 1,
                     "sidewall_angle_deg": 90, "selectivity": 100},
                ]):
                    self.request_json("POST", "/api/step/set", {"index": index, "params": params})
                asset = {
                    "version": 1, "id": "left_open", "name": "Left opening", "coordinate_unit": "nm",
                    "bounds_nm": [0, 0, 160, 160],
                    "layers": [{"id": "1/0", "layer": 1, "datatype": 0, "name": "Opening", "visible": True}],
                    "shapes": [{"id": "left", "type": "rectangle", "layer_id": "1/0", "x_nm": 0,
                                "y_nm": 0, "width_nm": 80, "height_nm": 160, "rotation_deg": 0}],
                    "source": {"kind": "editor"},
                }
                saved = self.request_json("POST", "/api/mask/asset/save", {"asset": asset, "step_index": 2})["result"]
                self.assertEqual(saved["step"]["params"]["mask_asset_revision"], saved["asset"]["revision"])
                self.assertEqual(saved["step"]["params"]["mask_asset_id"], "left_open")
                if missing_gdstk:
                    imported = self.request_json("POST", "/api/mask/asset/import?step_index=2",
                        raw_body=self.multipart("left.json", json.dumps(asset).encode()),
                        content_type="multipart/form-data; boundary=mask-e2e")["result"]
                    saved = imported
                    failure = self.request_json("GET", "/api/mask/asset/export?id=left_open&revision=2&format=gds", expected=400)
                    self.assertEqual(failure["code"], "dependency_missing")
                    failure = self.request_json("POST", "/api/mask/asset/import?step_index=2",
                        raw_body=self.multipart("missing.gds", b"GDS dependency probe"),
                        content_type="multipart/form-data; boundary=mask-e2e", expected=400)
                    self.assertEqual(failure["code"], "dependency_missing")
                initial = self.request_json("GET", "/api/preview/manifest?mode=solid")["result"]
                for index in range(4):
                    self.request_json("POST", "/api/run/step", {"index": index})
                developed = self.counts()
                resist_id = tcad.MaterialDatabase().id_for("Photoresist")
                silicon_id = tcad.MaterialDatabase().id_for("Silicon")
                self.assertLess(developed[0][resist_id], developed[1][resist_id])
                self.assertGreater(developed[1][resist_id], 0)
                self.request_json("POST", "/api/run/step", {"index": 4})
                etched = self.counts()
                self.assertLess(etched[0][silicon_id], etched[1][silicon_id])
                self.assertLess(etched[0][silicon_id], developed[0][silicon_id])
                recipe = self.request_json("GET", "/api/init")["result"]["recipe"]
                binding = recipe[2]["params"]
                bound_asset = self.request_json("GET", f'/api/mask/asset?id={binding["mask_asset_id"]}&revision={binding["mask_asset_revision"]}')["result"]
                self.assertEqual(bound_asset["sha256"], saved["asset"]["sha256"])
                self.assertEqual(binding["mask_asset_revision"], saved["asset"]["revision"])
                manifest = self.request_json("GET", "/api/preview/manifest?mode=solid")["result"]
                self.assertGreater(manifest["rev"], initial["rev"])
                mesh = manifest["meshes"][0]
                status, _, stl = self._request(self.base, self.cookie, "GET",
                    f'/api/preview/stl?mat_id={mesh["mat_id"]}&rev={manifest["rev"]}&mode=solid')
                self.assertEqual(status, 200)
                self.assertGreater(len(stl), 84)
                before_assets = self.request_json("GET", "/api/mask/assets")["result"]
                invalid = copy.deepcopy(asset)
                invalid["shapes"][0]["width_nm"] = -1
                for _ in range(2):
                    self.request_json("POST", "/api/mask/asset/save", {"asset": invalid, "step_index": 2}, expected=400)
                    self.assertEqual(self.request_json("GET", "/api/mask/assets")["result"], before_assets)
                    self.assertEqual(self.request_json("GET", "/api/init")["result"]["recipe"][2], recipe[2])
                    self.assertEqual(self.request_json("GET", "/api/preview/manifest?mode=solid")["result"], manifest)
                    self.assertEqual(self.counts(), etched)
                if missing_gdstk:
                    buffer = io.BytesIO()
                    mask = np.zeros((32, 32), dtype=bool)
                    mask[:16, :] = True
                    np.save(buffer, mask)
                    self.request_json("POST", "/api/upload/mask?step_index=2",
                        raw_body=self.multipart("legacy.npy", buffer.getvalue()),
                        content_type="multipart/form-data; boundary=mask-e2e")
                    legacy_params = self.request_json("GET", "/api/init")["result"]["recipe"][2]["params"]
                    self.assertTrue(legacy_params["mask_file"].endswith(".npy"))
                    self.assertEqual(legacy_params["mask_mode"], "Custom")
                    self.request_json("POST", "/api/reset", {})
                    self.request_json("POST", "/api/run/all", {})
                    legacy = self.counts()
                    self.assertLess(legacy[0][silicon_id], legacy[1][silicon_id])
            finally:
                manager.stop()

    def test_mask_asset_http_process_changes_geometry_and_rejects_invalid_retry(self):
        self.exercise()

    def test_no_gdstk_preserves_json_process_and_legacy_mask_file(self):
        with mock.patch.dict(sys.modules, {"gdstk": None}):
            self.exercise(missing_gdstk=True)
