# -*- coding: utf-8 -*-
"""layout：M6 LayoutAdapter（ADR-016）。

公共入口：归一化几何类型（MaskPolygon/LayoutGeometry/crop_roi）与
``LayoutAdapter``（GDS/OASIS 读写、布尔、栅格化）。引擎对象不越过本包边界。
"""
from .adapter import LayoutAdapter
from .geometry import LayoutGeometry, MaskPolygon, crop_roi

__all__ = ["LayoutAdapter", "LayoutGeometry", "MaskPolygon", "crop_roi"]
