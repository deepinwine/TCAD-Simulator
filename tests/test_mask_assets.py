from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

try:
    import gdstk
    HAS_GDSTK = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_GDSTK = False


def _candidate() -> dict:
    return {
        "version": 1,
        "id": "mask_metal1",
        "name": "Metal-1",
        "coordinate_unit": "nm",
        "bounds_nm": [0, 0, 2000, 2000],
        "layers": [
            {"id": "10/0", "layer": 10, "datatype": 0, "name": "Metal-1", "visible": True}
        ],
        "shapes": [
            {"id": "rect", "type": "rectangle", "layer_id": "10/0", "x_nm": 100,
             "y_nm": 100, "width_nm": 200, "height_nm": 300, "rotation_deg": 0},
            {"id": "circle", "type": "circle", "layer_id": "10/0", "cx_nm": 600,
             "cy_nm": 500, "radius_nm": 80},
            {"id": "hole", "type": "hole", "layer_id": "10/0", "cx_nm": 600,
             "cy_nm": 500, "radius_nm": 25},
            {"id": "line", "type": "line", "layer_id": "10/0",
             "points_nm": [[900, 200], [1100, 400]], "width_nm": 40},
            {"id": "poly", "type": "polygon", "layer_id": "10/0",
             "points_nm": [[1300, 200], [1500, 200], [1400, 400], [1300, 200]]},
        ],
        "source": {"kind": "editor"},
    }


class _Adapter:
    def __init__(self) -> None:
        self.raster_calls = []
        self.last_raster_geometry = None

    def rasterize(self, geometry, shape, bounds):
        self.raster_calls.append((geometry, tuple(shape), tuple(bounds)))
        self.last_raster_geometry = geometry
        return np.zeros((shape[1], shape[0]), dtype=bool)

    def read(self, path):
        from layout import LayoutGeometry, MaskPolygon
        return LayoutGeometry.from_polygons([
            MaskPolygon(np.asarray([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=float), 7, 2)
        ])

    def write(self, geometry, path, *, name="MASK"):
        Path(path).write_bytes(b"GDS-STUB")


class MaskAssetSchemaTests(unittest.TestCase):
    def test_topology_work_budget_is_preflighted_for_entire_candidate(self):
        from mask_assets import MaskAssetError, parse_candidate
        payload = _candidate()
        angles = np.linspace(0, math.tau, 1024, endpoint=False)
        points = np.column_stack((1000 + 500 * np.cos(angles), 1000 + 500 * np.sin(angles))).tolist()
        payload['shapes'] = [dict(id=f'p{i}', type='polygon', layer_id='10/0',
                                  points_nm=points + [points[0]]) for i in range(488)]
        with mock.patch('mask_assets.model._self_intersects', side_effect=AssertionError('must preflight')):
            with self.assertRaises(MaskAssetError) as caught:
                parse_candidate(payload)
        self.assertEqual(caught.exception.code, 'mask_asset_budget_exceeded')
        self.assertEqual(caught.exception.status, 413)

    def test_rejects_degenerate_polygon_topology(self):
        from mask_assets import MaskAssetError, parse_candidate
        for points in (
            [[0, 0], [100, 0], [100, 0], [0, 100], [0, 0]],
            [[0, 0], [100, 0], [50, 0], [50, 100], [0, 0]],
            [[0, 0], [100, 0], [200, 0], [0, 0]],
            [[0, 0], [100, 0], [100, 100], [50, 0], [0, 100], [0, 0]],
        ):
            payload = _candidate()
            payload['shapes'] = [dict(id='p', type='polygon', layer_id='10/0', points_nm=points)]
            with self.subTest(points=points), self.assertRaises(MaskAssetError):
                parse_candidate(payload)

    def test_shape_vertex_limits_are_checked_before_point_conversion(self):
        from mask_assets import MaskAssetError, parse_candidate
        for kind in ('polygon', 'line'):
            payload = _candidate()
            payload['shapes'] = [dict(id='p', type=kind, layer_id='10/0',
                                      points_nm=[None] * 2050, width_nm=1)]
            with self.subTest(kind=kind), self.assertRaises(MaskAssetError) as caught:
                parse_candidate(payload)
            self.assertEqual(caught.exception.code, 'mask_asset_budget_exceeded')

    def test_line_join_vertices_count_toward_asset_budget(self):
        from mask_assets import MaskAssetError, parse_candidate
        payload = _candidate()
        payload['shapes'] = [dict(id=f'l{i}', type='line', layer_id='10/0',
                                  points_nm=[[500 + (j % 2) * 100, 500] for j in range(1024)],
                                  width_nm=10) for i in range(8)]
        with self.assertRaises(MaskAssetError) as caught:
            parse_candidate(payload)
        self.assertEqual(caught.exception.code, 'mask_asset_budget_exceeded')
        self.assertEqual(caught.exception.params['limit'], 500_000)

    def test_asset_raster_uses_union_and_layer_local_hole_subtraction(self):
        from mask_assets import MaskAssetService, MaskAssetStore
        payload = _candidate()
        payload['bounds_nm'] = [0, 0, 2000, 1000]
        rect = dict(id='a', type='rectangle', layer_id='10/0', x_nm=0, y_nm=0,
                    width_nm=1500, height_nm=1000)
        hole = dict(id='h', type='hole', layer_id='10/0', cx_nm=750, cy_nm=500, radius_nm=200)
        cases = [([rect, dict(rect, id='b', x_nm=500)], True),
                 ([hole], False), ([rect, hole], False)]
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)))
            for shapes, center in cases:
                payload['shapes'] = shapes
                asset = service.save_candidate(payload)
                mask, _ = service.rasterize(asset.id, asset.revision, shape=(40, 20))
                self.assertEqual(mask.shape, (20, 40))
                self.assertEqual(bool(mask[10, 15]), center)
            payload['layers'].append(dict(id='20/0', layer=20, datatype=0, name='other'))
            payload['shapes'] = [rect, dict(hole, layer_id='20/0')]
            asset = service.save_candidate(payload)
            mask, _ = service.rasterize(asset.id, asset.revision, shape=(40, 20))
            self.assertTrue(mask[10, 15])

    def test_bent_line_joint_is_filled(self):
        from mask_assets import MaskAssetService, MaskAssetStore
        payload = _candidate()
        payload['shapes'] = [dict(id='l', type='line', layer_id='10/0',
                                  points_nm=[[500, 500], [1000, 500], [1000, 1000]], width_nm=200)]
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)))
            asset = service.save_candidate(payload)
            mask, _ = service.rasterize(asset.id, asset.revision, shape=(200, 200))
            self.assertTrue(mask[48:52, 98:102].all())

    def test_v1_shapes_convert_to_normalized_polygons(self):
        from mask_assets import parse_candidate, to_layout_geometry

        asset = parse_candidate(_candidate()).with_revision(1)
        geometry = to_layout_geometry(asset)

        self.assertEqual(asset.coordinate_unit, "nm")
        self.assertEqual(asset.revision, 1)
        self.assertEqual(len(geometry.polygons), 5)
        circle = geometry.polygons[1]
        self.assertEqual(circle.points.shape, (64, 2))
        self.assertEqual(geometry.polygons[2].points.shape, (64, 2))
        self.assertGreaterEqual(geometry.polygons[3].points.shape[0], 4)
        self.assertEqual(geometry.layers(), {(10, 0)})

    def test_even_odd_hole_is_respected_by_rasterizer(self):
        from layout import LayoutAdapter
        from mask_assets import parse_candidate, to_layout_geometry

        payload = _candidate()
        payload["shapes"] = [payload["shapes"][1], payload["shapes"][2]]
        geometry = to_layout_geometry(parse_candidate(payload).with_revision(1))
        adapter = object.__new__(LayoutAdapter)
        adapter._delegate = None
        adapter._gdstk = None
        adapter._backend = "test"
        mask = adapter.rasterize(geometry, shape=(200, 200), bounds=payload["bounds_nm"])
        self.assertFalse(mask[50, 60], "overlapping hole contour must toggle the circle center off")

    def test_rejects_invalid_schema_geometry_and_budgets(self):
        from mask_assets import MaskAssetError, parse_candidate

        mutations = []
        bad = _candidate(); bad["coordinate_unit"] = "um"; mutations.append(bad)
        bad = _candidate(); bad["shapes"][1]["id"] = "rect"; mutations.append(bad)
        bad = _candidate(); bad["shapes"][0]["layer_id"] = "99/0"; mutations.append(bad)
        bad = _candidate(); bad["shapes"][0]["x_nm"] = math.inf; mutations.append(bad)
        bad = _candidate(); bad["shapes"][0]["width_nm"] = -1; mutations.append(bad)
        bad = _candidate(); bad["shapes"][-1]["points_nm"][-1] = [1400, 450]; mutations.append(bad)
        bad = _candidate(); bad["shapes"][-1]["points_nm"] = [
            [1300, 200], [1500, 400], [1300, 400], [1500, 200], [1300, 200]
        ]; mutations.append(bad)
        bad = _candidate(); bad["shapes"][0]["x_nm"] = 1990; mutations.append(bad)
        bad = _candidate(); bad["shapes"] = [dict(bad["shapes"][0], id=f"s{i}") for i in range(50_001)]; mutations.append(bad)
        bad = _candidate(); bad["shapes"] = [{
            "id": "huge", "type": "polygon", "layer_id": "10/0",
            "points_nm": [[float(i % 1000), float((i // 1000) % 1000)] for i in range(500_001)] + [[0, 0]],
        }]; mutations.append(bad)

        for payload in mutations:
            with self.subTest(kind=payload.get("coordinate_unit"), count=len(payload.get("shapes", []))):
                with self.assertRaises(MaskAssetError):
                    parse_candidate(payload)


class MaskAssetStoreTests(unittest.TestCase):
    def test_revision_history_atomic_failure_and_reference_protection(self):
        from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore

        with tempfile.TemporaryDirectory() as temp_dir:
            store = MaskAssetStore(Path(temp_dir))
            service = MaskAssetService(store, adapter=_Adapter())
            first = service.save_candidate(_candidate())
            changed = _candidate(); changed["name"] = "Metal-1 changed"
            second = service.save_candidate(changed)
            self.assertEqual((first.revision, second.revision), (1, 2))
            self.assertEqual(store.get("mask_metal1", 1).name, "Metal-1")

            snapshot = {p.relative_to(Path(temp_dir)).as_posix(): p.read_bytes()
                        for p in Path(temp_dir).rglob("*") if p.is_file()}
            broken = _candidate(); broken["shapes"][0]["width_nm"] = -1
            with self.assertRaises(MaskAssetError):
                service.save_candidate(broken)
            self.assertEqual(snapshot, {p.relative_to(Path(temp_dir)).as_posix(): p.read_bytes()
                                        for p in Path(temp_dir).rglob("*") if p.is_file()})

            refs = [{"recipe": "current", "step_index": 3}]
            with self.assertRaises(MaskAssetError) as caught:
                service.delete("mask_metal1", references=refs)
            self.assertEqual(caught.exception.code, "mask_asset_in_use")
            self.assertEqual(caught.exception.params["references"], refs)

    def test_os_replace_failure_leaves_published_bytes_unchanged(self):
        from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore

        with tempfile.TemporaryDirectory() as temp_dir:
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)), adapter=_Adapter())
            service.save_candidate(_candidate())
            before = {p.relative_to(Path(temp_dir)).as_posix(): p.read_bytes()
                      for p in Path(temp_dir).rglob("*") if p.is_file()}
            with mock.patch("mask_assets.store.os.replace", side_effect=OSError("publish failed")):
                with self.assertRaises(MaskAssetError) as caught:
                    service.save_candidate(dict(_candidate(), name="failed"))
                self.assertEqual(caught.exception.code, 'mask_asset_apply_failed')
                self.assertIsInstance(caught.exception.__cause__, OSError)
            after = {p.relative_to(Path(temp_dir)).as_posix(): p.read_bytes()
                     for p in Path(temp_dir).rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_store_rejects_path_traversal_asset_ids(self):
        from mask_assets import MaskAssetError, MaskAssetStore

        with tempfile.TemporaryDirectory() as temp_dir:
            sibling = Path(temp_dir) / "escape"
            sibling.mkdir()
            secret = sibling / "secret.txt"
            secret.write_text("keep", encoding="utf-8")
            store = MaskAssetStore(Path(temp_dir))
            with self.assertRaises(MaskAssetError) as caught:
                store.delete("../escape")
            self.assertEqual(caught.exception.code, "invalid_mask_asset")
            self.assertEqual(secret.read_text(encoding="utf-8"), "keep")


class MaskAssetImportExportTests(unittest.TestCase):
    @unittest.skipUnless(HAS_GDSTK, "gdstk is not installed")
    def test_real_gds_export_reimport_preserves_hole_and_union_area(self):
        from mask_assets import MaskAssetService, MaskAssetStore
        payload = _candidate()
        payload['shapes'] = [dict(id='r', type='rectangle', layer_id='10/0',
                                  x_nm=0, y_nm=0, width_nm=2000, height_nm=2000),
                             dict(id='r2', type='rectangle', layer_id='10/0',
                                  x_nm=0, y_nm=0, width_nm=1000, height_nm=2000),
                             dict(id='h', type='hole', layer_id='10/0',
                                  cx_nm=1000, cy_nm=1000, radius_nm=300)]
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)))
            asset = service.save_candidate(payload)
            target = Path(temp_dir) / 'hole.gds'
            service.export_gds(asset.id, asset.revision, target)
            geometry = service._layout_adapter().read(target)
            area = sum(abs(float(np.dot(p.points[:, 0], np.roll(p.points[:, 1], 1))
                                 - np.dot(p.points[:, 1], np.roll(p.points[:, 0], 1)))) / 2
                       for p in geometry.polygons)
            expected = 4_000_000 - 64 * 300**2 * math.sin(math.tau / 64) / 2
            self.assertAlmostEqual(area, expected, delta=1500)
            imported = service.import_gds(target, asset_id='reimport', name='Reimport')
            mask, _ = service.rasterize(imported.id, imported.revision, shape=(200, 200))
            self.assertFalse(mask[100, 100])
            self.assertTrue(mask[20, 20])

    def test_json_round_trip_and_gds_adapter_boundary(self):
        from mask_assets import MaskAssetService, MaskAssetStore

        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = _Adapter()
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)), adapter=adapter)
            asset = service.import_json(json.dumps(_candidate()).encode("utf-8"))
            exported = json.loads(service.export_json(asset.id, asset.revision))
            self.assertEqual(exported["shapes"], _candidate()["shapes"])

            source = Path(temp_dir) / "source.gds"; source.write_bytes(b"stub")
            imported = service.import_gds(source, asset_id="from_gds", name="Imported")
            self.assertEqual(imported.layers[0].layer, 7)
            self.assertEqual(imported.layers[0].datatype, 2)
            self.assertEqual(imported.source["kind"], "gds")
            target = Path(temp_dir) / "out.gds"
            service.export_gds(imported.id, imported.revision, target)
            self.assertEqual(target.read_bytes(), b"GDS-STUB")

    @unittest.skipUnless(HAS_GDSTK, "gdstk is not installed")
    def test_real_gds_round_trip_preserves_database_unit_layers_and_area(self):
        from mask_assets import MaskAssetService, MaskAssetStore

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.gds"
            library = gdstk.Library(unit=2e-6, precision=1e-9)
            cell = library.new_cell("TOP")
            cell.add(gdstk.rectangle((0, 0), (1, 0.5), layer=7, datatype=2))
            library.write_gds(source)

            service = MaskAssetService(MaskAssetStore(Path(temp_dir)))
            imported = service.import_gds(source, asset_id="unit_gds", name="Unit GDS")
            self.assertEqual(imported.source["database_unit_m"], 2e-6)
            self.assertEqual(imported.source["database_precision_m"], 1e-9)
            self.assertEqual({(layer.layer, layer.datatype) for layer in imported.layers}, {(7, 2)})
            self.assertEqual(imported.bounds_nm, (0.0, 0.0, 2000.0, 1000.0))

            target = Path(temp_dir) / "round-trip.gds"
            service.export_gds(imported.id, imported.revision, target)
            round_trip = service._layout_adapter().read(target)
            self.assertEqual(round_trip.layers(), {(7, 2)})
            points = round_trip.polygons[0].points
            area = 0.5 * abs(float(np.dot(points[:, 0], np.roll(points[:, 1], 1))
                                   - np.dot(points[:, 1], np.roll(points[:, 0], 1))))
            self.assertAlmostEqual(area, 2_000_000.0, delta=1.0)

    def test_missing_gdstk_is_structured_and_does_not_break_json(self):
        from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore

        with tempfile.TemporaryDirectory() as temp_dir:
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)), adapter=None)
            with mock.patch("mask_assets.service.LayoutAdapter", side_effect=ImportError("gdstk")):
                with self.assertRaises(MaskAssetError) as caught:
                    service.import_gds(Path(temp_dir) / "missing.gds", asset_id="g", name="G")
            self.assertEqual(caught.exception.code, "dependency_missing")
            self.assertEqual(caught.exception.params, {"dependency": "gdstk"})
            self.assertEqual(service.import_json(json.dumps(_candidate())).revision, 1)


class MaskAssetExposureTests(unittest.TestCase):
    class _Model:
        def __init__(self) -> None:
            self.open_mask = np.zeros((20, 10), dtype=bool)
            self.voxel_size_nm = 100.0
            self.calls = []

        def expose_resist(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    def test_exposure_reads_exact_revision_and_records_content_hash(self):
        from layout import LayoutAdapter
        from mask_assets import MaskAssetService, MaskAssetStore
        from tcad_simulator import ExposureStep, MaterialDatabase

        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = object.__new__(LayoutAdapter)
            adapter._delegate = None
            adapter._gdstk = None
            adapter._backend = "normalized"
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)), adapter=adapter)
            first_payload = _candidate()
            first_payload["bounds_nm"] = [0, 0, 2000, 1000]
            first_payload["shapes"] = [{
                "id": "left", "type": "rectangle", "layer_id": "10/0",
                "x_nm": 0, "y_nm": 0, "width_nm": 1000, "height_nm": 1000,
            }]
            first = service.save_candidate(first_payload)
            second_payload = _candidate()
            second_payload["bounds_nm"] = [0, 0, 2000, 1000]
            second_payload["shapes"] = [{
                "id": "right", "type": "rectangle", "layer_id": "10/0",
                "x_nm": 1000, "y_nm": 0, "width_nm": 1000, "height_nm": 1000,
            }]
            service.save_candidate(second_payload)

            step = ExposureStep(MaterialDatabase())
            step.params.update({
                "mask_mode": "Asset",
                "mask_asset_id": first.id,
                "mask_asset_revision": first.revision,
            })
            step.bind_mask_asset_service(service)
            model = self._Model()
            step.execute(model)

            self.assertEqual(len(model.calls), 1)
            mask = model.calls[0][1]["mask_override"]
            self.assertEqual(mask.shape, (20, 10))
            self.assertTrue(mask[:10, :].all())
            self.assertFalse(mask[10:, :].any())
            self.assertEqual(step.last_metrics["mask_asset_revision"], 1)
            self.assertEqual(step.last_metrics["mask_sha256"], first.sha256)
            self.assertEqual(first.sha256, service.get(first.id, 1).sha256)

    def test_missing_revision_fails_before_model_mutation(self):
        from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore
        from tcad_simulator import ExposureStep, MaterialDatabase

        with tempfile.TemporaryDirectory() as temp_dir:
            service = MaskAssetService(MaskAssetStore(Path(temp_dir)), adapter=_Adapter())
            service.save_candidate(_candidate())
            step = ExposureStep(MaterialDatabase())
            step.params.update({
                "mask_mode": "Asset", "mask_asset_id": "mask_metal1", "mask_asset_revision": 99,
            })
            step.bind_mask_asset_service(service)
            model = self._Model()
            with self.assertRaises(MaskAssetError):
                step.execute(model)
            self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()
