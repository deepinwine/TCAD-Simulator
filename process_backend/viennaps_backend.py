# -*- coding: utf-8 -*-
"""ViennaPSBackend：几何精度工艺后端（M9，ADR-014/021）。

实现 M7 的 :class:`ProcessBackend` 接口，内部驱动 ViennaPS level-set 引擎。
能力模型：显式支持 Initialize Wafer 与 Etch(Dry)；其余步骤抛出
``unsupported_step`` 并建议回退体素后端（绝不静默改用别的物理）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from .base import (
    BackendInfo,
    BackendModelSummary,
    ProcessBackend,
    ProcessBackendError,
    StepOutcome,
)

SUPPORTED_STEPS = frozenset({"Initialize Wafer", "Etch"})
PHYSICAL_EXTENT_NM = 640.0


def engine_available() -> bool:
    try:
        import viennaps  # noqa: F401

        return True
    except ImportError:
        return False


class ViennaPSBackend(ProcessBackend):
    """几何精度后端：表面网格为权威表示（体素网格不适用）。"""

    def __init__(
        self,
        grid_nm: float = 8.0,
        physical_extent_nm: float = PHYSICAL_EXTENT_NM,
    ) -> None:
        if not engine_available():
            raise ProcessBackendError(
                "ViennaPS 引擎不可用（构建步骤见 experiments/viennaps/README.md）",
                code="engine_missing",
            )
        import viennaps as ps

        ps.setDimension(3)
        ps.setNumThreads(4)
        ps.Length.setUnit("um")
        ps.Time.setUnit("s")
        self._ps = ps
        self._grid_nm = max(1.0, float(grid_nm))
        self._extent_um = float(physical_extent_nm) / 1000.0
        self._domain = None

    # ---- 接口 ------------------------------------------------------------

    def info(self) -> BackendInfo:
        ps = self._ps
        return BackendInfo(
            name="viennaps",
            precision="geometry",
            version=str(getattr(ps, "__version__", "unknown")),
        )

    def summary(self) -> BackendModelSummary:
        grid = max(1, int(round(self._extent_um * 1000.0 / self._grid_nm)))
        return BackendModelSummary(
            grid_shape=(grid, grid, grid),  # 名义栅格（供 UI 展示）
            voxel_size_nm=self._grid_nm,
        )

    def capabilities(self) -> Dict[str, Any]:
        return {
            "supported_steps": sorted(SUPPORTED_STEPS),
            "fallback": "voxel",
        }

    def execute_step(self, step: Any) -> StepOutcome:
        name = str(getattr(step, "name", ""))
        params = dict(getattr(step, "params", {}) or {})
        if name == "Initialize Wafer":
            return self._initialize(params)
        if name == "Etch":
            chemistry = str(params.get("chemistry", "Dry"))
            if chemistry.lower() != "dry":
                raise ProcessBackendError(
                    f"Etch chemistry={chemistry!r} 暂无 ViennaPS 模型映射",
                    code="unsupported_step",
                )
            return self._etch(params)
        raise ProcessBackendError(
            f"步骤 {name!r} 不在 ViennaPS 能力集内（支持：{sorted(SUPPORTED_STEPS)}）",
            code="unsupported_step",
            suggestion="请使用体素后端（create_backend('voxel')）运行完整配方",
        )

    def snapshot(self) -> Any:
        self._require_domain()
        copy = self._ps.Domain()
        copy.deepCopy(self._domain)
        return copy

    def restore(self, state: Any) -> None:
        self._domain = state

    def material_surfaces(
        self, face_limit: int = 20000
    ) -> List[Tuple[int, np.ndarray]]:
        self._require_domain()
        import tcad_simulator as tcad

        database = tcad.MaterialDatabase()
        silicon_id = next(
            mid for mid, material in database.items() if material.name == "Silicon"
        )
        mesh = self._domain.getSurfaceMesh()
        nodes = np.asarray(mesh.getNodes(), dtype=float)
        cells = np.asarray(mesh.getTriangles(), dtype=np.int64)
        if nodes.size == 0 or cells.size == 0:
            return []
        triangles = nodes[cells.reshape(-1, 3)][:, :, :3]
        if len(triangles) > int(face_limit):
            stride = max(1, len(triangles) // int(face_limit))
            triangles = triangles[::stride]
        return [(silicon_id, triangles)]

    def grid(self) -> np.ndarray:
        raise ProcessBackendError(
            "几何后端没有体素网格；使用 material_surfaces() 获取表面网格",
            code="geometry_backend",
        )

    def shutdown(self) -> None:
        self._domain = None

    # ---- 内部 ------------------------------------------------------------

    def _require_domain(self) -> None:
        if self._domain is None:
            raise ProcessBackendError(
                "尚未初始化几何（先执行 Initialize Wafer）",
                code="no_geometry",
            )

    def _initialize(self, params: Dict[str, Any]) -> StepOutcome:
        ps = self._ps
        thickness_nm = float(params.get("thickness_nm", 200.0))
        self._domain = ps.Domain()
        ps.MakeTrench(
            self._domain,
            gridDelta=self._grid_nm / 1000.0,
            xExtent=self._extent_um,
            yExtent=self._extent_um,
            trenchWidth=self._extent_um * 2.0,  # 全开：平衬底
            trenchDepth=thickness_nm / 1000.0,
        ).apply()
        return StepOutcome(message=f"ViennaPS 平衬底（{thickness_nm:.0f} nm Si）")

    def _etch(self, params: Dict[str, Any]) -> StepOutcome:
        ps = self._ps
        self._require_domain()
        duration = float(params.get("time", 30.0))
        model_params = ps.SF6O2Etching.defaultParameters()
        # 参数映射标定（M9，2026-09-02）：隔离扫描证实速率对通量高度线性
        # （≈0.76 nm/s/单位，顶面下降法）；据此定标 flux=13 对齐体素基准
        # 10nm/s。⚠ 已知未解：backend 路径下标定测试实测仅 ~1nm/30s（z 参考
        # 点疑锚定在掩膜/侧壁沿而非腔底——下一步在后端路径复刻扫描测量排障）。
        model_params.etchantFlux = 100.0
        model_params.ionFlux = 100.0
        model = ps.SF6O2Etching(model_params)
        process = ps.Process(self._domain, model)
        process.setProcessDuration(duration)
        cov = ps.CoverageParameters()
        cov.tolerance = 1e-3
        process.setParameters(cov)
        process.apply()
        return StepOutcome(
            message=f"ViennaPS SF6O2 干法刻蚀 {duration:.0f}s（默认通量参数）",
        )
