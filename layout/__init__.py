# -*- coding: utf-8 -*-
"""layout：M6 LayoutAdapter（ADR-016）。

公共入口：归一化几何类型（MaskPolygon/LayoutGeometry/crop_roi）与
``LayoutAdapter``（GDS/OASIS 读写、布尔、栅格化）。引擎对象不越过本包边界。
"""
from .adapter import LayoutAdapter
from .geometry import LayoutGeometry, MaskPolygon, crop_roi
from .klayout_backend import KLayoutAdapter
from .litho import configure_exposure_step, mask_from_layout, write_mask_npy

__all__ = [
    "KLayoutAdapter",
    "LayoutAdapter",
    "LayoutGeometry",
    "MaskPolygon",
    "configure_exposure_step",
    "crop_roi",
    "mask_from_layout",
    "write_mask_npy",
]
