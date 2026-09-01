# -*- coding: utf-8 -*-
"""光刻桥接（ADR-016）：归一化版图 → 曝光步骤可消费的布尔掩膜。

只产出 numpy 布尔栅格与 .npy 文件——与 ``load_mask_from_file``/
``resample_mask`` 的既有语义对齐；引擎对象不进入光刻。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import numpy as np

from .adapter import LayoutAdapter
from .geometry import LayoutGeometry, crop_roi


def mask_from_layout(
    source: Union[str, Path, LayoutGeometry],
    shape: Tuple[int, int],
    bounds: Optional[Tuple[float, float, float, float]] = None,
    layers: Optional[Iterable[Tuple[int, int]]] = None,
    roi: Optional[Tuple[float, float, float, float]] = None,
    adapter: Optional[LayoutAdapter] = None,
) -> np.ndarray:
    """GDS/OASIS 文件或归一化几何 → 布尔掩膜栅格 (ny, nx)。

    bounds 缺省用几何自身包围盒；layers 过滤参与的图层；roi 先裁剪再栅格化。
    """
    engine = adapter if adapter is not None else LayoutAdapter()
    if isinstance(source, LayoutGeometry):
        geometry = source
    else:
        geometry = engine.read(source)
    if layers is not None:
        geometry = geometry.for_layers(list(layers))
    if roi is not None:
        geometry = crop_roi(geometry, *roi)
    if not geometry.polygons:
        return np.zeros((int(shape[0]), int(shape[1])), dtype=bool)
    window = bounds if bounds is not None else geometry.bounds
    return engine.rasterize(geometry, shape=shape, bounds=window)


def write_mask_npy(grid: np.ndarray, path: Union[str, Path]) -> Path:
    """把布尔栅格写成曝光步骤可直接引用的 .npy 掩膜文件。"""
    mask = np.asarray(grid).astype(bool)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.save(target, mask)
    return target


def configure_exposure_step(step, mask_path: Union[str, Path], name: str) -> None:
    """按既有上传语义配置 ExposureStep 使用该掩膜文件。

    与 WebUI 上传处理器设置的参数一致：``mask_mode=Custom``、``mask_file``、
    ``mask_name``。
    """
    step.params["mask_mode"] = "Custom"
    step.params["mask_file"] = str(mask_path)
    step.params["mask_name"] = str(name)
    if getattr(step, "custom_mask", None) is not None:
        step.custom_mask = None
    if getattr(step, "image_mask", None) is not None:
        step.image_mask = None
