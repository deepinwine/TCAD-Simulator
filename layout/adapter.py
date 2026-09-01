# -*- coding: utf-8 -*-
"""LayoutAdapter：GDS/OASIS 读写、布尔运算与栅格化的引擎边界（ADR-016）。

当前后端 gdstk（必备）；KLayout 为可选（T3）。所有公开方法只进出
:mod:`layout.geometry` 的归一化类型，不泄漏引擎对象。
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np

from .geometry import LayoutGeometry, MaskPolygon

GDS_UNIT_M = 1e-6
GDS_PRECISION_M = 1e-9
_NM_PER_UNIT = 1000.0  # unit=1µm → 坐标×1000 得 nm


class LayoutAdapter:
    """版图适配器（每实例一个引擎选择）。"""

    def __init__(self, backend: str = "gdstk") -> None:
        if backend != "gdstk":
            raise ValueError(f"未知或未安装的版图后端：{backend!r}")
        import gdstk  # 延迟导入：无 gdstk 的环境仍可用 geometry 纯函数

        self._gdstk = gdstk
        self._backend = backend

    @property
    def backend(self) -> str:
        return self._backend

    @staticmethod
    def probe() -> dict:
        backends: List[str] = []
        try:
            import gdstk  # noqa: F401

            backends.append("gdstk")
        except ImportError:
            pass
        try:
            import klayout.db  # noqa: F401

            backends.append("klayout")
        except ImportError:
            pass
        return {"backends": backends, "default": backends[0] if backends else None}

    # ---- 读写 -----------------------------------------------------------

    def read(self, path) -> LayoutGeometry:
        source = Path(path)
        suffix = source.suffix.lower()
        gdstk = self._gdstk
        if suffix == ".oas":
            library = gdstk.read_oas(source)
        elif suffix == ".gds":
            library = gdstk.read_gds(source)
        else:
            raise ValueError(f"不支持的版图文件：{suffix!r}（仅 .gds/.oas）")
        polygons: List[MaskPolygon] = []
        for polygon in library.cells[0].polygons if False else _iter_polygons(library):
            points = np.asarray(polygon.points, dtype=float) * _NM_PER_UNIT
            polygons.append(MaskPolygon(
                points=points,
                layer=int(polygon.layer),
                datatype=int(polygon.datatype),
            ))
        return LayoutGeometry.from_polygons(polygons)

    def write(self, geometry: LayoutGeometry, path, *, name: str = "MASK") -> None:
        gdstk = self._gdstk
        library = gdstk.Library(unit=GDS_UNIT_M, precision=GDS_PRECISION_M)
        cell = library.new_cell(name)
        for polygon in geometry.polygons:
            cell.add(gdstk.Polygon(
                polygon.points / _NM_PER_UNIT,
                layer=polygon.layer,
                datatype=polygon.datatype,
            ))
        target = Path(path)
        if target.suffix.lower() == ".oas":
            library.write_oas(target)
        else:
            library.write_gds(target)

    # ---- 布尔 ------------------------------------------------------------

    def boolean(
        self,
        a: LayoutGeometry,
        b: LayoutGeometry,
        op: str,
        *,
        layer: int = 1,
        datatype: int = 0,
    ) -> LayoutGeometry:
        if op not in {"and", "or", "not", "sub", "xor"}:
            raise ValueError(f"未知布尔操作：{op!r}")
        gdstk = self._gdstk
        polys_a = [gdstk.Polygon(p.points / _NM_PER_UNIT, layer=p.layer, datatype=p.datatype) for p in a.polygons]
        polys_b = [gdstk.Polygon(p.points / _NM_PER_UNIT, layer=p.layer, datatype=p.datatype) for p in b.polygons]
        if op == "or":
            results = gdstk.boolean(polys_a, polys_b, "or")
        elif op == "and":
            results = gdstk.boolean(polys_a, polys_b, "and")
        elif op in {"not", "sub"}:
            results = gdstk.boolean(polys_a, polys_b, "not")
        else:
            results = gdstk.boolean(polys_a, polys_b, "xor")
        polygons: List[MaskPolygon] = []
        for result in results:
            points = np.asarray(result.points, dtype=float) * _NM_PER_UNIT
            polygons.append(MaskPolygon(points=points, layer=layer, datatype=datatype))
        return LayoutGeometry.from_polygons(polygons)

    # ---- 栅格化（光刻桥接） ----------------------------------------------

    def rasterize(
        self,
        geometry: LayoutGeometry,
        shape,
        bounds,
    ) -> np.ndarray:
        """归一化几何 → 布尔栅格（even-odd 填充，像素中心采样）。

        shape=(nx, ny)，bounds=(x0, y0, x1, y1)（nm）。返回数组的行对应 y、
        列对应 x，与 ExposureStep custom mask 的 (ny, nx) 栅格一致。
        """
        nx, ny = int(shape[0]), int(shape[1])
        x0, y0, x1, y1 = (float(v) for v in bounds)
        if nx <= 0 or ny <= 0 or x1 <= x0 or y1 <= y0:
            raise ValueError("rasterize 参数非法")
        grid = np.zeros((ny, nx), dtype=bool)
        xs = x0 + (np.arange(nx) + 0.5) * (x1 - x0) / nx
        ys = y0 + (np.arange(ny) + 0.5) * (y1 - y0) / ny
        crossings = np.zeros((ny, nx), dtype=np.int32)
        for polygon in geometry.polygons:
            crossings += _polygon_crossings(polygon.points, xs, ys)
        grid[:] = (crossings % 2) == 1
        return grid


def _polygon_crossings(points: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """每个像素中心的多边形射线交叉计数（向 +x 方向）。"""
    ny, nx = ys.shape[0], xs.shape[0]
    crossings = np.zeros((ny, nx), dtype=np.int32)
    count = points.shape[0]
    for index in range(count):
        x_a, y_a = points[index]
        x_b, y_b = points[(index + 1) % count]
        if y_a == y_b:
            continue
        lo, hi = (y_a, y_b) if y_a < y_b else (y_b, y_a)
        rows = np.nonzero((ys > lo) & (ys <= hi))[0]
        if rows.size == 0:
            continue
        x_intersect = x_a + (ys[rows] - y_a) * (x_b - x_a) / (y_b - y_a)
        for row_index, x_hit in zip(rows, x_intersect):
            crossings[row_index] += (xs > x_hit).astype(np.int32)
    return crossings


def _iter_polygons(library):
    """展平所有 cell（含引用）并产出多边形。"""
    top_level = library.top_level() if hasattr(library, "top_level") else library.cells
    for cell in top_level:
        for polygon in cell.polygons:
            yield polygon
        for reference in cell.references:
            for polygon in _flatten_reference(reference):
                yield polygon


def _flatten_reference(reference, depth: int = 0):
    if depth > 16:
        return
    cell = reference.cell
    origin = np.asarray(reference.origin, dtype=float)
    for polygon in cell.polygons:
        points = np.asarray(polygon.points, dtype=float)
        yield _translated_polygon(polygon, points + origin)
    for nested in cell.references:
        for polygon in _flatten_reference(
            nested,
            depth + 1,
        ):
            yield _translated_polygon(
                polygon,
                np.asarray(polygon.points, dtype=float)
                + np.asarray(nested.origin, dtype=float)
                + origin,
            )


def _translated_polygon(polygon, points_um):
    import gdstk

    return gdstk.Polygon(
        points_um,
        layer=int(polygon.layer),
        datatype=int(polygon.datatype),
    )
