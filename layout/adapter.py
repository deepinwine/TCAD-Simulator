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
        if backend == "klayout":
            from .klayout_backend import KLayoutAdapter

            self._delegate = KLayoutAdapter()
            self._gdstk = None
            self._backend = "klayout"
            return
        if backend != "gdstk":
            raise ValueError(f"未知或未安装的版图后端：{backend!r}")
        import gdstk  # 延迟导入：无 gdstk 的环境仍可用 geometry 纯函数

        self._delegate = None
        self._gdstk = gdstk
        self._backend = backend

    @classmethod
    def normalized(cls) -> "LayoutAdapter":
        """Create the dependency-free normalized-geometry rasterizer."""
        adapter = cls.__new__(cls)
        adapter._delegate = None
        adapter._gdstk = None
        adapter._backend = "normalized"
        return adapter

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
        geometry, _metadata = self.read_with_metadata(path)
        return geometry

    def read_with_metadata(self, path):
        """Read normalized geometry plus scalar source-unit metadata."""
        if self._delegate is not None:
            return self._delegate.read(path), {}
        source = Path(path)
        suffix = source.suffix.lower()
        gdstk = self._gdstk
        if suffix == ".oas":
            library = gdstk.read_oas(source)
        elif suffix == ".gds":
            library = gdstk.read_gds(source)
        else:
            raise ValueError(f"不支持的版图文件：{suffix!r}（仅 .gds/.oas）")
        nm_per_unit = float(library.unit) * 1e9
        polygons: List[MaskPolygon] = []
        for polygon in _iter_polygons(library):
            points = np.asarray(polygon.points, dtype=float) * nm_per_unit
            polygons.append(MaskPolygon(
                points=points,
                layer=int(polygon.layer),
                datatype=int(polygon.datatype),
            ))
        return LayoutGeometry.from_polygons(polygons), {
            "database_unit_m": float(library.unit),
            "database_precision_m": float(library.precision),
        }

    def write(self, geometry: LayoutGeometry, path, *, name: str = "MASK") -> None:
        if self._delegate is not None:
            return self._delegate.write(geometry, path, name=name)
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
        if self._delegate is not None:
            return self._delegate.boolean(a, b, op, layer=layer, datatype=datatype)
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

    def fracture(self, geometry: LayoutGeometry) -> LayoutGeometry:
        """Split Boolean contours into simple polygons for editable GDS import.

        GDS represents holes with doubled bridge edges. Small fragments avoid
        admitting those weakly simple contours into the asset polygon schema.
        """
        if self._delegate is not None:
            raise ValueError("Simple polygon fracture requires the gdstk backend")
        polygons = []
        for item in geometry.polygons:
            source = self._gdstk.Polygon(item.points / _NM_PER_UNIT,
                                         layer=item.layer, datatype=item.datatype)
            for piece in source.fracture(max_points=5, precision=GDS_PRECISION_M / GDS_UNIT_M):
                polygons.append(MaskPolygon(np.asarray(piece.points) * _NM_PER_UNIT,
                                            item.layer, item.datatype))
        return LayoutGeometry.from_polygons(polygons)

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
    """Budget expansion before asking gdstk to apply the complete hierarchy."""
    top_level = library.top_level() if hasattr(library, "top_level") else library.cells
    if not top_level and library.cells:
        raise ValueError("Layout hierarchy contains a cycle")
    totals = [0, 0, 0]
    cache = {}
    for cell in top_level:
        counts = _hierarchy_budget(cell, cache, set())
        totals = [a + b for a, b in zip(totals, counts)]
        _check_expansion_budget(totals)
    for cell in top_level:
        yield from cell.get_polygons(apply_repetitions=True, include_paths=True)


def _check_expansion_budget(counts):
    # Separate from asset validation: these caps protect native flatten allocation.
    if any(value > limit for value, limit in zip(counts, (100_000, 500_000, 100_000))):
        raise ValueError("Layout expansion budget exceeded (polygons, vertices or references)")


def _hierarchy_budget(cell, cache, active):
    key = id(cell)
    if key in active or len(active) >= 64:
        raise ValueError("Layout hierarchy contains a cycle or exceeds depth budget")
    if key in cache:
        return cache[key]
    if not hasattr(cell, "polygons"):
        raise ValueError("Unresolved layout cell reference")
    active.add(key)
    counts = [0, 0, 0]
    for polygon in cell.polygons:
        copies = max(1, polygon.repetition.size)
        counts[0] += copies
        counts[1] += copies * polygon.size
        _check_expansion_budget(counts)
    for path in cell.paths:
        copies = max(1, path.repetition.size)
        _check_expansion_budget([counts[0] + copies * path.num_paths, counts[1], counts[2]])
        _check_path_budget(path, copies, counts)
        # to_polygons does not expand repetitions; count them before flattening.
        for polygon in path.to_polygons():
            counts[0] += copies
            counts[1] += copies * polygon.size
            _check_expansion_budget(counts)
    for reference in cell.references:
        copies = max(1, reference.repetition.size)
        counts[2] += copies
        _check_expansion_budget(counts)
        nested = _hierarchy_budget(reference.cell, cache, active)
        counts = [a + copies * b for a, b in zip(counts, nested)]
        _check_expansion_budget(counts)
    active.remove(key)
    cache[key] = counts
    return counts


def _check_path_budget(path, copies, counts):
    """Bound native path discretization before allocating polygon contours.

    File readers produce linear FlexPaths at the library's default tolerance.
    In-memory parametric paths must also fit a conservative evaluation budget;
    reject excessive precision rather than silently changing their geometry.
    """
    sections = max(1, path.size)
    multiplier = copies * path.num_paths
    tolerance = float(path.tolerance)
    if not np.isfinite(tolerance) or tolerance < 1e-6:
        raise ValueError("Layout path precision exceeds expansion budget")
    if any(callable(value) for value in path.ends):
        raise ValueError("Custom path callbacks exceed expansion budget")
    if hasattr(path, "max_evals"):
        if any(value in ("round", "smooth") for value in path.ends):
            raise ValueError("Parametric curved path caps exceed expansion budget")
        # Adaptive subdivision may round max_evals up to the next power of two;
        # both contour sides together require at most 4 * max_evals per section.
        estimate = 4 * max(1, path.max_evals) * sections * multiplier
    else:
        estimate = 4 * sections * multiplier
        _check_expansion_budget([counts[0], counts[1] + estimate, counts[2]])
        if any(callable(value) for value in path.ends + path.joins):
            raise ValueError("Custom path callbacks exceed expansion budget")
        curved = any(value in ("round", "smooth") for value in path.ends + path.joins)
        radii = path.bend_radius
        if curved or any(radii):
            radius = max(float(np.max(path.widths(), initial=0)), *radii)
            # A generous bound for circular caps, joins and bends per spine point.
            estimate *= max(1, int(np.ceil(8 * np.sqrt(radius / tolerance))))
    _check_expansion_budget([counts[0], counts[1] + estimate, counts[2]])
