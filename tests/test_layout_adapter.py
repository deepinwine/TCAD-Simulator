# -*- coding: utf-8 -*-
"""M6 T1：归一化掩膜几何（纯函数）与 gdstk LayoutAdapter。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from layout import (
    LayoutAdapter,
    LayoutGeometry,
    MaskPolygon,
    crop_roi,
)

try:
    import gdstk  # noqa: F401
    HAS_GDSTK = True
except ImportError:  # pragma: no cover
    HAS_GDSTK = False


def rect(x0: float, y0: float, x1: float, y1: float, layer: int = 1, datatype: int = 0) -> MaskPolygon:
    return MaskPolygon(
        points=np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float),
        layer=layer,
        datatype=datatype,
    )


def geometry_of(*polygons: MaskPolygon) -> LayoutGeometry:
    return LayoutGeometry.from_polygons(list(polygons))


def polygon_area(polygon: MaskPolygon) -> float:
    pts = polygon.points
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def geometry_area(geometry: LayoutGeometry) -> float:
    return sum(polygon_area(p) for p in geometry.polygons)


class GeometryTests(unittest.TestCase):
    def test_bounds_and_layers(self) -> None:
        geo = geometry_of(rect(0, 0, 100, 50, layer=1), rect(200, 10, 300, 60, layer=2))
        self.assertEqual(geometry_area(geo), 100 * 50 + 100 * 50)
        self.assertEqual(tuple(geo.bounds), (0.0, 0.0, 300.0, 60.0))
        self.assertEqual(geo.layers(), {(1, 0), (2, 0)})

    def test_layer_filter(self) -> None:
        geo = geometry_of(rect(0, 0, 10, 10, layer=1), rect(0, 0, 10, 10, layer=2))
        only1 = geo.for_layers([(1, 0)])
        self.assertEqual(len(only1.polygons), 1)
        self.assertEqual(only1.polygons[0].layer, 1)

    def test_crop_roi_fully_inside_keeps_polygon(self) -> None:
        geo = geometry_of(rect(10, 10, 20, 20))
        cropped = crop_roi(geo, 0, 0, 100, 100)
        self.assertEqual(geometry_area(cropped), 100.0)

    def test_crop_roi_fully_outside_drops_polygon(self) -> None:
        geo = geometry_of(rect(10, 10, 20, 20))
        cropped = crop_roi(geo, 500, 500, 600, 600)
        self.assertEqual(len(cropped.polygons), 0)

    def test_crop_roi_clips_overlapping_polygon(self) -> None:
        geo = geometry_of(rect(0, 0, 100, 100))
        cropped = crop_roi(geo, 50, 0, 150, 100)
        self.assertEqual(len(cropped.polygons), 1)
        self.assertAlmostEqual(geometry_area(cropped), 50 * 100, places=6)


@unittest.skipUnless(HAS_GDSTK, "gdstk 未安装")
class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = LayoutAdapter()
        self.tmp = Path(tempfile.mkdtemp(prefix="tcad-m6-"))

    def test_backend_is_gdstk(self) -> None:
        self.assertEqual(self.adapter.backend, "gdstk")
        capabilities = LayoutAdapter.probe()
        self.assertIn("gdstk", capabilities["backends"])

    def test_write_read_round_trip(self) -> None:
        geo = geometry_of(
            rect(0, 0, 1000, 500, layer=1),
            rect(2000, 0, 3000, 500, layer=2, datatype=5),
        )
        path = self.tmp / "rt.gds"
        self.adapter.write(geo, path)
        loaded = self.adapter.read(path)
        self.assertEqual(loaded.layers(), {(1, 0), (2, 5)})
        self.assertAlmostEqual(geometry_area(loaded), 1000 * 500 * 2, delta=1.0)
        self.assertAlmostEqual(loaded.bounds[0], 0.0, delta=1.0)
        self.assertAlmostEqual(loaded.bounds[2], 3000.0, delta=1.0)

    def test_oasis_round_trip(self) -> None:
        geo = geometry_of(rect(0, 0, 200, 200, layer=3))
        path = self.tmp / "rt.oas"
        self.adapter.write(geo, path)
        loaded = self.adapter.read(path)
        self.assertEqual(loaded.layers(), {(3, 0)})
        self.assertAlmostEqual(geometry_area(loaded), 200 * 200, delta=1.0)

    def test_read_flattens_hierarchy(self) -> None:
        import gdstk

        lib = gdstk.Library(unit=1e-6, precision=1e-9)
        cell_tile = lib.new_cell("TILE")
        cell_tile.add(gdstk.rectangle((0, 0), (1, 1), layer=7))
        top = lib.new_cell("TOP")
        top.add(gdstk.Reference(cell_tile, origin=(0, 0)))
        top.add(gdstk.Reference(cell_tile, origin=(2, 0)))
        path = self.tmp / "hier.gds"
        lib.write_gds(path)
        loaded = self.adapter.read(path)
        tiles = [p for p in loaded.polygons if p.layer == 7]
        self.assertEqual(len(tiles), 2)
        self.assertAlmostEqual(geometry_area(loaded), 2 * (1000 * 1000), delta=1.0)

    def test_boolean_sub_and_and(self) -> None:
        a = geometry_of(rect(0, 0, 100, 100))
        b = geometry_of(rect(50, 0, 150, 100))
        sub = self.adapter.boolean(a, b, "sub")
        self.assertAlmostEqual(geometry_area(sub), 50 * 100, delta=1.0)
        both = self.adapter.boolean(a, b, "and")
        self.assertAlmostEqual(geometry_area(both), 50 * 100, delta=1.0)
        union = self.adapter.boolean(a, b, "or")
        self.assertAlmostEqual(geometry_area(union), 150 * 100, delta=1.0)

    def test_boolean_output_is_normalized(self) -> None:
        a = geometry_of(rect(0, 0, 100, 100))
        b = geometry_of(rect(200, 200, 300, 300))
        result = self.adapter.boolean(a, b, "xor")
        self.assertIsInstance(result, LayoutGeometry)
        for polygon in result.polygons:
            self.assertIsInstance(polygon, MaskPolygon)
            self.assertEqual(polygon.points.dtype, float)
        self.assertAlmostEqual(geometry_area(result), 2 * 100 * 100, delta=1.0)

    def test_rasterize_rect_matches_grid(self) -> None:
        geo = geometry_of(rect(0, 0, 100, 100))
        grid = self.adapter.rasterize(geo, shape=(10, 10), bounds=(0.0, 0.0, 100.0, 100.0))
        self.assertEqual(grid.shape, (10, 10))
        self.assertEqual(grid.dtype, bool)
        self.assertTrue(bool(grid.all()))

        half = crop_roi(geo, 0, 0, 50, 100)
        grid2 = self.adapter.rasterize(half, shape=(10, 10), bounds=(0.0, 0.0, 100.0, 100.0))
        self.assertTrue(bool(grid2[:, :5].all()))
        self.assertFalse(bool(grid2[:, 5:].any()))

    def test_rasterize_even_odd_rule_for_hole(self) -> None:
        outer = rect(0, 0, 100, 100)
        inner = rect(25, 25, 75, 75)
        ring = LayoutGeometry.from_polygons([outer, inner])
        grid = self.adapter.rasterize(ring, shape=(10, 10), bounds=(0.0, 0.0, 100.0, 100.0))
        # 中心 5x5 像素区域应为空心（even-odd）
        self.assertFalse(bool(grid[3:8, 3:8].any()))
        self.assertTrue(bool(grid[:3, :].all()))


if __name__ == "__main__":
    unittest.main()


import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from layout import configure_exposure_step, mask_from_layout, write_mask_npy  # noqa: E402


@unittest.skipUnless(HAS_GDSTK, "gdstk 未安装")
class LithoBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tcad-m6-t2-"))
        self.adapter = LayoutAdapter()

    def test_mask_from_gds_left_half(self) -> None:
        geo = geometry_of(rect(0, 0, 500, 1000, layer=1))
        gds = self.tmp / "half.gds"
        self.adapter.write(geo, gds)
        grid = mask_from_layout(gds, shape=(10, 10), bounds=(0.0, 0.0, 1000.0, 1000.0))
        self.assertEqual(grid.shape, (10, 10))
        self.assertTrue(bool(grid[:, :5].all()))
        self.assertFalse(bool(grid[:, 5:].any()))

    def test_mask_layers_and_roi(self) -> None:
        geo = geometry_of(
            rect(0, 0, 500, 1000, layer=1),
            rect(500, 0, 1000, 1000, layer=2),
        )
        only2 = mask_from_layout(geo, shape=(10, 10), layers=[(2, 0)], bounds=(0.0, 0.0, 1000.0, 1000.0))
        self.assertFalse(bool(only2[:, :5].any()))
        self.assertTrue(bool(only2[:, 5:].all()))
        roi = mask_from_layout(geo, shape=(10, 10), roi=(250, 0, 750, 1000), bounds=(0.0, 0.0, 1000.0, 1000.0))
        self.assertFalse(bool(roi[:, :3].any()))
        self.assertTrue(bool(roi[:, 3:7].all()))

    def test_npy_round_trip_through_runtime_loader(self) -> None:
        import tcad_simulator as tcad

        grid = mask_from_layout(
            geometry_of(rect(0, 0, 400, 1000, layer=1)),
            shape=(8, 8),
        )
        path = write_mask_npy(grid, self.tmp / "mask.npy")
        loaded = tcad.load_mask_from_file(str(path))
        np.testing.assert_array_equal(loaded, grid)

    def test_end_to_end_gds_exposure_develop(self) -> None:
        import tcad_simulator as tcad

        # GDS：左半开口掩膜
        geo = geometry_of(rect(0, 0, 320, 640, layer=1))
        gds = self.tmp / "flow.gds"
        self.adapter.write(geo, gds)
        grid = mask_from_layout(gds, shape=(64, 64), bounds=(0.0, 0.0, 640.0, 640.0))
        mask_path = write_mask_npy(grid, self.tmp / "flow-mask.npy")

        database = tcad.MaterialDatabase()
        model = tcad.ProcessModel(
            database,
            grid_shape=(64, 64, 64),
            voxel_size_nm=640.0 / 64,
            max_workers=1,
        )
        try:
            tcad.InitializeWaferStep(database).execute(model)
            tcad.SpinResistStep(database).execute(model)

            exposure = tcad.ExposureStep(database)
            configure_exposure_step(exposure, mask_path, "gds-left-half")
            exposure.execute(model)
            tcad.DevelopStep(database).execute(model)

            resist_id = next(
                mid for mid, material in database.items()
                if material.name == "Photoresist"
            )
            resist = model.grid == resist_id
            self.assertGreater(int(resist.sum()), 0)
            # 左半曝光显影后应无光刻胶，右半保留
            self.assertEqual(int(resist[:, :32].sum()), 0)
            self.assertGreater(int(resist[:, 32:].sum()), 0)
        finally:
            model.parallel.shutdown()


@unittest.skipUnless(
    __import__("layout.klayout_backend", fromlist=["_klayout_available"])._klayout_available(),
    "klayout 未安装（可选后端）",
)
class KLayoutBackendTests(unittest.TestCase):
    """与 gdstk 后端同语义的回归（需真实 KLayout 环境）。"""

    def setUp(self) -> None:
        from layout import KLayoutAdapter

        self.adapter = KLayoutAdapter()
        self.tmp = Path(tempfile.mkdtemp(prefix="tcad-m6-kl-"))

    def test_round_trip_and_boolean(self) -> None:
        geo = geometry_of(rect(0, 0, 1000, 500, layer=1))
        path = self.tmp / "rt.gds"
        self.adapter.write(geo, path)
        loaded = self.adapter.read(path)
        self.assertEqual(loaded.layers(), {(1, 0)})
        self.assertAlmostEqual(geometry_area(loaded), 1000 * 500, delta=1.0)

        b = geometry_of(rect(500, 0, 1500, 500))
        sub = self.adapter.boolean(geo, b, "sub")
        self.assertAlmostEqual(geometry_area(sub), 500 * 500, delta=1.0)


class KLayoutAbsenceTests(unittest.TestCase):
    def test_unavailable_backend_raises_clearly(self) -> None:
        from layout.klayout_backend import _klayout_available

        if _klayout_available():
            self.skipTest("klayout 已安装")
        from layout import KLayoutAdapter

        with self.assertRaises(ValueError) as ctx:
            KLayoutAdapter()
        self.assertIn("klayout", str(ctx.exception))
