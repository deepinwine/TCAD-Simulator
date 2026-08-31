# -*- coding: utf-8 -*-
"""M4 T5：/api/v2 FastAPI 适配层（只读端点，复用 facade 序列化形状）。"""
from __future__ import annotations

import os
import struct
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_FASTAPI = False

GRID = 48


@unittest.skipUnless(HAS_FASTAPI, "fastapi 未安装（可选依赖）")
class ApiV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from process_api.http import create_app

        cls.client = TestClient(create_app(grid=GRID))
        super().setUpClass()

    def test_health(self) -> None:
        response = self.client.get("/api/v2/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "process_api")
        self.assertEqual(payload["version"], 2)

    def test_init_returns_contract_shape(self) -> None:
        response = self.client.get("/api/v2/init")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()), {"recipe", "model", "factories", "materials", "uiState"},
        )
        self.assertGreater(len(payload["recipe"]), 0)
        self.assertIn("Silicon", [m["name"] for m in payload["materials"]])
        self.assertEqual(payload["model"]["gridShape"], [GRID, GRID, GRID])
        self.assertEqual(
            set(payload["recipe"][0].keys()),
            {
                "index", "name", "instanceName", "group", "loop", "enabled",
                "params", "parameterSpecs", "runtimeStatus",
            },
        )

    def test_init_unknown_demo_returns_error_envelope(self) -> None:
        response = self.client.get("/api/v2/init", params={"demo": "__no_such_demo__"})
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "unknown_demo")

    def test_manifest_shape_and_stl_binary(self) -> None:
        manifest = self.client.get("/api/v2/preview/manifest").json()
        self.assertIn("revision", manifest)
        self.assertIn("meshes", manifest)
        silicon = [m for m in manifest["meshes"] if m["name"] == "Silicon"]
        self.assertEqual(len(silicon), 1)
        mesh = silicon[0]
        self.assertEqual(
            set(mesh.keys()),
            {"materialId", "name", "triangleCount", "boundingBox", "visual"},
        )

        stl = self.client.get(
            "/api/v2/preview/stl",
            params={"materialId": mesh["materialId"], "revision": manifest["revision"]},
        )
        self.assertEqual(stl.status_code, 200)
        self.assertEqual(stl.headers["content-type"], "application/octet-stream")
        data = stl.content
        count = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(count, mesh["triangleCount"])
        self.assertEqual(len(data), 84 + 50 * count)

    def test_stl_stale_revision_error_envelope(self) -> None:
        manifest = self.client.get("/api/v2/preview/manifest").json()
        stale = manifest["revision"] + 100
        response = self.client.get(
            "/api/v2/preview/stl",
            params={"materialId": 1, "revision": stale},
        )
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "stale_revision")


if __name__ == "__main__":
    unittest.main()
