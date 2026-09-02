# -*- coding: utf-8 -*-
"""M15：标定量测与误差指标。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass(frozen=True)
class ReferenceTarget:
    """参考结构目标值（来源可标定）。"""
    source_type: str  # 'synthetic' | 'literature' | 'measured'
    source: str  # 具体出处描述
    target_depth_nm: Optional[float] = None
    top_cd_nm: Optional[float] = None
    bottom_cd_nm: Optional[float] = None
    sidewall_angle_deg: Optional[float] = None
    film_thickness_nm: Optional[float] = None
    step_coverage: Optional[float] = None
    material_volume_nm3: Optional[float] = None


@dataclass
class MeasurementResult:
    """从仿真几何中量测的值。"""
    depth_nm: Optional[float] = None
    top_cd_nm: Optional[float] = None
    bottom_cd_nm: Optional[float] = None
    sidewall_angle_deg: Optional[float] = None
    film_thickness_nm: Optional[float] = None
    step_coverage: Optional[float] = None
    material_volume_nm3: Optional[float] = None


@dataclass
class CalibrationMetrics:
    """每个指标的误差。"""
    depth_error_pct: Optional[float] = None
    top_cd_error_pct: Optional[float] = None
    bottom_cd_error_pct: Optional[float] = None
    sidewall_angle_error_deg: Optional[float] = None
    film_thickness_error_pct: Optional[float] = None
    volume_error_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in vars(self).items() if v is not None}

    def max_error_pct(self) -> float:
        errors = [
            abs(v) for v in [
                self.depth_error_pct,
                self.top_cd_error_pct,
                self.bottom_cd_error_pct,
                self.film_thickness_error_pct,
                self.volume_error_pct,
            ] if v is not None
        ]
        return max(errors) if errors else 0.0


def compare_to_reference(
    measured: MeasurementResult,
    reference: ReferenceTarget,
) -> CalibrationMetrics:
    """对比量测结果与参考目标，产出各指标误差。"""
    def _pct(actual: float, target: float) -> float:
        if target == 0:
            return 0.0
        return round((actual - target) / target * 100, 2)

    return CalibrationMetrics(
        depth_error_pct=(
            _pct(measured.depth_nm, reference.target_depth_nm)
            if measured.depth_nm is not None and reference.target_depth_nm is not None
            else None
        ),
        top_cd_error_pct=(
            _pct(measured.top_cd_nm, reference.top_cd_nm)
            if measured.top_cd_nm is not None and reference.top_cd_nm is not None
            else None
        ),
        bottom_cd_error_pct=(
            _pct(measured.bottom_cd_nm, reference.bottom_cd_nm)
            if measured.bottom_cd_nm is not None and reference.bottom_cd_nm is not None
            else None
        ),
        sidewall_angle_error_deg=(
            round(measured.sidewall_angle_deg - reference.sidewall_angle_deg, 2)
            if measured.sidewall_angle_deg is not None and reference.sidewall_angle_deg is not None
            else None
        ),
        film_thickness_error_pct=(
            _pct(measured.film_thickness_nm, reference.film_thickness_nm)
            if measured.film_thickness_nm is not None and reference.film_thickness_nm is not None
            else None
        ),
        volume_error_pct=(
            _pct(measured.material_volume_nm3, reference.material_volume_nm3)
            if measured.material_volume_nm3 is not None and reference.material_volume_nm3 is not None
            else None
        ),
    )


def measure_etch_depth(
    surfaces: list,
    backend_name: str = "unknown",
) -> MeasurementResult:
    """从后端 material_surfaces 量测刻蚀深度（顶面下降法）。"""
    if not surfaces:
        return MeasurementResult()
    triangles = surfaces[0][1]
    if triangles.size == 0:
        return MeasurementResult()
    z_values = triangles[:, :, 2]
    depth = float(z_values.max() - z_values.min())
    return MeasurementResult(depth_nm=depth * 1000.0)  # µm → nm


def measure_film_thickness(
    scene,
    material_name: str = "",
) -> MeasurementResult:
    """从 GeometryScene 量测指定材料的薄膜厚度。"""
    for mesh in scene.meshes:
        if material_name.lower() in mesh.name.lower():
            pts = mesh.triangles.reshape(-1, 3)
            thickness = float(pts[:, 2].max() - pts[:, 2].min())
            return MeasurementResult(film_thickness_nm=thickness)
    return MeasurementResult()
