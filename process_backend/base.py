# -*- coding: utf-8 -*-
"""ProcessBackend 抽象接口：M7 为 M8/M9 预留的引擎接缝。

契约不变：步骤仍经 ``ProcessStep.execute(model)`` 驱动 ``ProcessModel``；
VoxelBackend 只是包装。能力模型（显式回退）在 M9 引入。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np


class ProcessBackendError(Exception):
    """后端选择/执行失败的结构化错误（suggestion 给出回退指引）。"""

    def __init__(self, message: str, *, code: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.suggestion = suggestion


@dataclass(frozen=True)
class BackendInfo:
    name: str
    precision: str  # 'voxel' | 'geometry'（M9 ViennaPS 为 geometry）
    version: str


@dataclass(frozen=True)
class BackendModelSummary:
    grid_shape: Tuple[int, int, int]
    voxel_size_nm: float


@dataclass(frozen=True)
class StepOutcome:
    message: str
    metrics: Dict[str, Any] | None = None


class ProcessBackend(ABC):
    """工艺后端接口：执行步骤、快照恢复、几何提取、模型摘要。"""

    @abstractmethod
    def info(self) -> BackendInfo:
        """后端标识与精度类别。"""

    @abstractmethod
    def summary(self) -> BackendModelSummary:
        """当前模型摘要。"""

    @abstractmethod
    def execute_step(self, step: Any) -> StepOutcome:
        """执行一个工艺步骤（委托架构契约，物理不在此层）。"""

    @abstractmethod
    def snapshot(self) -> Dict[str, Any]:
        """捕获可恢复的模型状态。"""

    @abstractmethod
    def restore(self, state: Dict[str, Any]) -> None:
        """恢复模型状态。"""

    @abstractmethod
    def material_surfaces(
        self, face_limit: int = 20000
    ) -> List[Tuple[int, np.ndarray]]:
        """提取各材料表面三角面片（与 ProcessModel 语义一致）。"""

    @abstractmethod
    def grid(self) -> np.ndarray:
        """体素网格只读视图（voxel 后端语义；geometry 后端 M9 定义）。"""

    @abstractmethod
    def shutdown(self) -> None:
        """释放并行资源。"""
