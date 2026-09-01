# -*- coding: utf-8 -*-
"""归一化掩膜几何（ADR-016）：纯数据 + 纯函数，坐标一律 nm。

引擎对象（gdstk/KLayout）绝不越过 :mod:`layout.adapter` 边界进入本模块
或任何工艺代码；光刻只消费这里的类型。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import numpy as np

LayerKey = Tuple[int, int]


@dataclass(frozen=True)
class MaskPolygon:
    """单个掩膜多边形（顶点按序，nm 坐标）。"""

    points: np.ndarray
    layer: int
    datatype: int

    def __post_init__(self) -> None:
        points = np.asarray(self.points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or points.shape[0] < 3:
            raise ValueError("MaskPolygon.points 必须是 (N, 2) 且 N >= 3")
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "layer", int(self.layer))
        object.__setattr__(self, "datatype", int(self.datatype))


@dataclass(frozen=True)
class LayoutGeometry:
    """归一化版图几何：多边形集合 + 整体包围盒（nm）。"""

    polygons: Tuple[MaskPolygon, ...]
    bounds: Tuple[float, float, float, float]

    @classmethod
    def from_polygons(cls, polygons: Sequence[MaskPolygon]) -> "LayoutGeometry":
        if not polygons:
            return cls(polygons=(), bounds=(0.0, 0.0, 0.0, 0.0))
        all_points = np.concatenate([p.points for p in polygons], axis=0)
        mins = all_points.min(axis=0)
        maxs = all_points.max(axis=0)
        return cls(
            polygons=tuple(polygons),
            bounds=(float(mins[0]), float(mins[1]), float(maxs[0]), float(maxs[1])),
        )

    def layers(self) -> set:
        return {(p.layer, p.datatype) for p in self.polygons}

    def for_layers(self, keys: Iterable[LayerKey]) -> "LayoutGeometry":
        wanted = set(keys)
        return LayoutGeometry.from_polygons(
            [p for p in self.polygons if (p.layer, p.datatype) in wanted]
        )


def _clip_polygon_against_edge(
    points: np.ndarray, keep_from: float, keep_to: float, axis: int
) -> np.ndarray:
    """Sutherland–Hodgman 单边裁剪（窗口为轴对齐矩形 → 各边凸）。"""
    def inside(point: np.ndarray) -> bool:
        return keep_from <= point[axis] <= keep_to

    clipped: List[np.ndarray] = []
    count = points.shape[0]
    for index in range(count):
        current = points[index]
        nxt = points[(index + 1) % count]
        current_in = inside(current)
        nxt_in = inside(nxt)
        if current_in:
            clipped.append(current)
        if current_in != nxt_in:
            # 端点越过的窗口边界：由外侧端点位置决定
            outside = nxt if not nxt_in else current
            boundary = keep_from if outside[axis] < keep_from else keep_to
            delta = nxt[axis] - current[axis]
            if delta == 0:
                continue
            t = (boundary - current[axis]) / delta
            clipped.append(current + t * (nxt - current))
    if not clipped:
        return np.zeros((0, 2), dtype=float)
    return np.stack(clipped, axis=0)


def crop_roi(
    geometry: LayoutGeometry,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> LayoutGeometry:
    """按轴对齐 ROI（nm）裁剪几何；完全在外的多边形被丢弃。"""
    kept: List[MaskPolygon] = []
    for polygon in geometry.polygons:
        points = polygon.points
        mins = points.min(axis=0)
        maxs = points.max(axis=0)
        if maxs[0] < x0 or mins[0] > x1 or maxs[1] < y0 or mins[1] > y1:
            continue
        if mins[0] >= x0 and maxs[0] <= x1 and mins[1] >= y0 and maxs[1] <= y1:
            kept.append(polygon)
            continue
        clipped = points
        for axis, (lo, hi) in enumerate(((x0, x1), (y0, y1))):
            clipped = _clip_polygon_against_edge(clipped, lo, hi, axis)
            if clipped.shape[0] < 3:
                break
        if clipped.shape[0] >= 3:
            kept.append(MaskPolygon(points=clipped, layer=polygon.layer, datatype=polygon.datatype))
    return LayoutGeometry.from_polygons(kept)
