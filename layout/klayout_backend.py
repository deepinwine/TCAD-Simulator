# -*- coding: utf-8 -*-
"""KLayout 可选后端（ADR-016）：与 gdstk 后端同语义的归一化进出。

KLayout 未安装时导入本模块不报错（仅 ``KLayoutAdapter`` 构造抛出明确错误）；
能力探测见 ``LayoutAdapter.probe``。本环境（macOS/arm64，镜像 403）暂未验证
真实 KLayout 运行——测试以 skipUnless 保护，语义与 gdstk 后端对齐。
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np

from .geometry import LayoutGeometry, MaskPolygon


def _klayout_available() -> bool:
    try:
        import klayout.db  # noqa: F401

        return True
    except ImportError:
        return False


class KLayoutAdapter:
    """与 :class:`layout.adapter.LayoutAdapter` 同语义的 KLayout 实现。"""

    def __init__(self) -> None:
        if not _klayout_available():
            raise ValueError(
                "KLayout 后端不可用：未安装 klayout 包（pip install klayout）"
            )
        import klayout.db as kdb

        self._kdb = kdb

    @property
    def backend(self) -> str:
        return "klayout"

    def _to_nm(self, layout, points) -> np.ndarray:
        # klayout 多边形顶点为整数 DBU；dbu 单位为 µm
        dbu_nm = float(layout.dbu) * 1000.0
        return np.asarray(points, dtype=float) * dbu_nm

    def _from_nm(self, layout, points_nm: np.ndarray):
        dbu_nm = float(layout.dbu) * 1000.0
        return points_nm / dbu_nm

    def read(self, path) -> LayoutGeometry:
        kdb = self._kdb
        layout = kdb.Layout()
        source = Path(path)
        if source.suffix.lower() == ".oas":
            layout.read(str(source), kdb.LoadLayoutOptions(oas=True))
        else:
            layout.read(str(source))
        polygons: List[MaskPolygon] = []
        layer_infos = layout.layer_infos()
        for cell in layout.top_cells():
            for layer_index, info in enumerate(layer_infos):
                shapes = cell.shapes(layout.layer(info))
                for shape in shapes.each():
                    if not shape.is_polygon and not shape.is_box:
                        continue
                    polygon = shape.polygon if shape.is_polygon else shape.box.convert_to_polygon()
                    pts = np.array(
                        [[point.x, point.y] for point in polygon.each_point_hull()],
                        dtype=float,
                    )
                    if pts.shape[0] < 3:
                        continue
                    polygons.append(MaskPolygon(
                        points=self._to_nm(layout, pts),
                        layer=int(info.layer),
                        datatype=int(info.datatype),
                    ))
        return LayoutGeometry.from_polygons(polygons)

    def write(self, geometry: LayoutGeometry, path, *, name: str = "MASK") -> None:
        kdb = self._kdb
        layout = kdb.Layout()
        layout.dbu = 0.001  # 1 DBU = 1 nm
        cell = layout.create_cell(name)
        for polygon in geometry.polygons:
            layer_index = layout.layer(polygon.layer, polygon.datatype)
            pts = self._from_nm(layout, polygon.points)
            hull = [kdb.DPoint(float(x), float(y)) for x, y in pts]
            cell.shapes(layer_index).insert(kdb.DPolygon(hull))
        target = Path(path)
        options = None
        if target.suffix.lower() == ".oas":
            options = kdb.SaveLayoutOptions()
            options.oas = True
        layout.write(str(target), options)

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
        kdb = self._kdb
        layout = kdb.Layout()
        layout.dbu = 0.001

        def region_of(geometry: LayoutGeometry):
            region = kdb.Region()
            for polygon in geometry.polygons:
                pts = self._from_nm(layout, polygon.points)
                region.insert(kdb.DPolygon([
                    kdb.DPoint(float(x), float(y)) for x, y in pts
                ]))
            return region

        region_a = region_of(a)
        region_b = region_of(b)
        if op == "and":
            result = region_a & region_b
        elif op == "or":
            result = region_a | region_b
        elif op in {"not", "sub"}:
            result = region_a - region_b
        else:
            result = region_a ^ region_b
        polygons: List[MaskPolygon] = []
        for dpolygon in result.each():
            pts = np.array(
                [[point.x, point.y] for point in dpolygon.each_point_hull()],
                dtype=float,
            )
            if pts.shape[0] < 3:
                continue
            polygons.append(MaskPolygon(
                points=self._to_nm(layout, pts),
                layer=layer,
                datatype=datatype,
            ))
        return LayoutGeometry.from_polygons(polygons)
