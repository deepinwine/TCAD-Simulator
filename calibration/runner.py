# -*- coding: utf-8 -*-
"""M15：标定运行器——参数扫描 → 仿真 → 量测 → 对比 → 评分。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .metrics import (
    CalibrationMetrics,
    MeasurementResult,
    ReferenceTarget,
    compare_to_reference,
)


@dataclass
class CalibrationProfile:
    """标定配置：工艺 + 引擎 + 参数 + 参考目标。"""
    name: str
    process: str  # 'dry_etch' | 'isotropic_etch' | 'conformal_deposition'
    engine: str  # 'viennaps' | 'voxel'
    engine_version: str = ""
    material: str = ""
    parameter_grid: Dict[str, List[float]] = field(default_factory=dict)
    reference: Optional[ReferenceTarget] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "process": self.process,
            "engine": self.engine,
            "reference": vars(self.reference) if self.reference else None,
            "parameter_grid": self.parameter_grid,
        }


@dataclass
class CalibrationResult:
    """单次标定评估结果。"""
    profile_name: str
    parameters: Dict[str, float]
    metrics: CalibrationMetrics
    score: float  # max_error_pct，越低越好
    elapsed_s: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile_name,
            "parameters": self.parameters,
            "metrics": self.metrics.to_dict(),
            "score": self.score,
            "elapsed_s": round(self.elapsed_s, 2),
        }


@dataclass
class CalibrationReport:
    """标定运行完整报告。"""
    profile_name: str
    engine: str
    engine_version: str
    git_commit: str
    grid_resolution: str
    timestamp: str
    results: List[CalibrationResult] = field(default_factory=list)
    best: Optional[CalibrationResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile_name,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "git_commit": self.git_commit,
            "grid_resolution": self.grid_resolution,
            "timestamp": self.timestamp,
            "results": [r.to_dict() for r in self.results],
            "best": self.best.to_dict() if self.best else None,
        }


class CalibrationRunner:
    """标定运行器：支持参数扫描（grid search）。

    用法：
        runner = CalibrationRunner(simulate_fn, measure_fn)
        report = runner.run(profile)
    """

    def __init__(
        self,
        simulate_fn: Callable[[Dict[str, float]], list],
        measure_fn: Callable[[list], MeasurementResult],
    ) -> None:
        """simulate_fn(params) → surfaces; measure_fn(surfaces) → MeasurementResult。"""
        self._simulate = simulate_fn
        self._measure = measure_fn

    def run(
        self,
        profile: CalibrationProfile,
        git_commit: str = "",
        grid_resolution: str = "",
    ) -> CalibrationReport:
        import subprocess
        from datetime import datetime

        if profile.reference is None:
            raise ValueError(f"profile {profile.name!r} 缺少 reference target")

        try:
            commit = git_commit or subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except Exception:
            commit = git_commit

        report = CalibrationReport(
            profile_name=profile.name,
            engine=profile.engine,
            engine_version=profile.engine_version,
            git_commit=commit,
            grid_resolution=grid_resolution,
            timestamp=datetime.now().isoformat(),
        )

        for params in self._grid_iterate(profile.parameter_grid):
            started = time.perf_counter()
            surfaces = self._simulate(params)
            measured = self._measure(surfaces)
            metrics = compare_to_reference(measured, profile.reference)
            elapsed = time.perf_counter() - started
            result = CalibrationResult(
                profile_name=profile.name,
                parameters=params,
                metrics=metrics,
                score=metrics.max_error_pct(),
                elapsed_s=elapsed,
            )
            report.results.append(result)

        if report.results:
            report.best = min(report.results, key=lambda r: r.score)

        return report

    @staticmethod
    def _grid_iterate(
        parameter_grid: Dict[str, List[float]],
    ) -> List[Dict[str, float]]:
        """笛卡尔积参数扫描。"""
        if not parameter_grid:
            return [{}]
        keys = list(parameter_grid.keys())
        combos: List[Dict[str, float]] = [{}]
        for key in keys:
            values = parameter_grid[key]
            new_combos = []
            for combo in combos:
                for value in values:
                    new_combos.append({**combo, key: value})
            combos = new_combos
        return combos
