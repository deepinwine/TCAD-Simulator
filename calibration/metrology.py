# -*- coding: utf-8 -*-
"""M21: MetrologyEngine——基于 ROI 的物理量测（BUG-004 修复）。

取代旧的 measure_etch_depth()（用 z-range 冒充 etch depth）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class MeasurementROI:
    """量测感兴趣区域（nm）。"""
    x_min: float = float("-inf")
    x_max: float = float("inf")
    y_min: float = float("-inf")
    y_max: float = float("inf")
    z_min: float = float("-inf")
    z_max: float = float("inf")

    def contains(self, x: float, y: float, z: float) -> bool:
        return (self.x_min <= x <= self.x_max
                and self.y_min <= y <= self.y_max
                and self.z_min <= z <= self.z_max)


@dataclass
class EtchDepthResult:
    """刻蚀深度量测结果。"""
    depth_nm: float = 0.0
    reference_z_nm: float = 0.0
    bottom_z_nm: float = 0.0
    method: str = "surface_descent"


class MetrologyEngine:
    """基于几何的物理量测引擎。"""

    @staticmethod
    def etch_depth(
        surfaces_before: list,
        surfaces_after: list,
        roi: Optional[MeasurementROI] = None,
    ) -> EtchDepthResult:
        """BUG-004 fix: 刻蚀深度 = 刻蚀前参考面 z_max − 刻蚀后底部 z_min。

        只在同一 ROI 内比较，避免 mask/侧壁干扰。
        """
        if roi is None:
            roi = MeasurementROI()

        def _roi_points(triangles: np.ndarray) -> np.ndarray:
            pts = triangles.reshape(-1, 3)
            mask = (
                (pts[:, 0] >= roi.x_min) & (pts[:, 0] <= roi.x_max)
                & (pts[:, 1] >= roi.y_min) & (pts[:, 1] <= roi.y_max)
                & (pts[:, 2] >= roi.z_min) & (pts[:, 2] <= roi.z_max)
            )
            return pts[mask] if mask.any() else pts

        # 刻蚀前：顶面 z_max（参考面）
        if not surfaces_before:
            return EtchDepthResult(method="no_before")
        pts_before = _roi_points(surfaces_before[0][1])
        ref_z = float(pts_before[:, 2].max())

        # 刻蚀后：新的顶面 z_max（顶面下降法 = 表面消耗量）
        if not surfaces_after:
            return EtchDepthResult(reference_z_nm=ref_z, method="no_after")
        pts_after = _roi_points(surfaces_after[0][1])
        # BUG-004 fix: 用 z_max（新表面），不是 z_min（材料底部）
        bottom_z = float(pts_after[:, 2].max())

        depth = (ref_z - bottom_z) * 1000.0  # µm → nm
        return EtchDepthResult(
            depth_nm=max(0.0, depth),
            reference_z_nm=ref_z,
            bottom_z_nm=bottom_z,
            method="surface_descent",
        )

    @staticmethod
    def critical_dimension(
        triangles: np.ndarray,
        z_plane: float,
        axis: str = "x",
    ) -> float:
        """在指定 z 平面量测 CD（临界尺寸）。返回 nm。"""
        pts = triangles.reshape(-1, 3)
        tolerance = 0.005  # µm tolerance for z-plane intersection
        mask = np.abs(pts[:, 2] - z_plane) <= tolerance
        if not mask.any():
            return 0.0
        on_plane = pts[mask]
        if axis == "x":
            cd = float(on_plane[:, 0].max() - on_plane[:, 0].min())
        else:
            cd = float(on_plane[:, 1].max() - on_plane[:, 1].min())
        return cd * 1000.0  # µm → nm

    @staticmethod
    def film_thickness(
        scene,
        material_name: str = "",
    ) -> float:
        """量测指定材料的薄膜厚度。返回 nm。"""
        for mesh in scene.meshes:
            if material_name.lower() in mesh.name.lower():
                pts = mesh.triangles.reshape(-1, 3)
                return float(pts[:, 2].max() - pts[:, 2].min())
        return 0.0

    @staticmethod
    def step_coverage(
        scene,
        top_material: str = "",
        bottom_material: str = "",
    ) -> float:
        """Step coverage = bottom_thickness / top_thickness。"""
        engine = MetrologyEngine()
        top = engine.film_thickness(scene, top_material)
        bottom = engine.film_thickness(scene, bottom_material)
        if top <= 0:
            return 0.0
        return bottom / top
