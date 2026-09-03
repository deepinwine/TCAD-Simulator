# -*- coding: utf-8 -*-
"""M15：物理标定框架。

目标：可重复的模型标定——参数集 → 仿真 → 量测 → 对比参考 → 评分。
项目定位：physics-inspired / reference-calibrated topography simulation。
"""
from .metrics import CalibrationMetrics, MeasurementResult, ReferenceTarget, compare_to_reference
from .runner import CalibrationRunner, CalibrationProfile

__all__ = ["CalibrationMetrics", "CalibrationProfile", "CalibrationRunner", "MeasurementResult", "ReferenceTarget", "compare_to_reference"]
from .metrology import MeasurementROI, MetrologyEngine
