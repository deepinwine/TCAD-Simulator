# -*- coding: utf-8 -*-
"""VoxelBackend：现有 ProcessModel 的行为不变包装（M7）。"""
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

PHYSICAL_EXTENT_NM = 640.0


class VoxelBackend(ProcessBackend):
    """包装 :class:`tcad_simulator.ProcessModel`；物理全部委托既有契约。"""

    def __init__(self, grid: int = 64, physical_extent_nm: float = PHYSICAL_EXTENT_NM) -> None:
        import tcad_simulator as tcad

        self._tcad = tcad
        self._grid = max(32, int(grid))
        self._voxel_nm = float(physical_extent_nm) / self._grid
        self._database = tcad.MaterialDatabase()
        self._model = tcad.ProcessModel(
            self._database,
            grid_shape=(self._grid, self._grid, self._grid),
            voxel_size_nm=self._voxel_nm,
            max_workers=1,
        )

    @property
    def database(self):
        return self._database

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="voxel",
            precision="voxel",
            version=self._tcad.__version__ if hasattr(self._tcad, "__version__") else "1",
        )

    def summary(self) -> BackendModelSummary:
        return BackendModelSummary(
            grid_shape=(self._grid, self._grid, self._grid),
            voxel_size_nm=self._voxel_nm,
        )

    def execute_step(self, step: Any) -> StepOutcome:
        try:
            message = step.execute(self._model)
        except Exception as exc:  # noqa: BLE001 - 结构化错误而非崩溃
            raise ProcessBackendError(
                str(exc), code="step_failed",
            ) from exc
        metrics = getattr(step, "last_metrics", None)
        return StepOutcome(
            message=str(message),
            metrics=metrics if isinstance(metrics, dict) else None,
        )

    def snapshot(self) -> Dict[str, Any]:
        try:
            return self._model.snapshot_state(compression="dense")
        except TypeError:
            return self._model.snapshot_state()

    def restore(self, state: Dict[str, Any]) -> None:
        self._model.restore_state(state)

    def material_surfaces(
        self, face_limit: int = 20000
    ) -> List[Tuple[int, np.ndarray]]:
        return self._model.get_material_surfaces(face_limit=face_limit)

    def grid(self) -> np.ndarray:
        return self._model.grid

    def shutdown(self) -> None:
        try:
            self._model.parallel.shutdown()
        except Exception:
            pass


_BACKEND_FACTORIES = {
    "voxel": VoxelBackend,
}


def create_backend(name: str, **kwargs) -> ProcessBackend:
    """注册表：M8 的 viennaps 沙盒将在此登记 'viennaps'。"""
    factory = _BACKEND_FACTORIES.get(str(name))
    if factory is None:
        raise ProcessBackendError(
            f"未知工艺后端：{name!r}",
            code="unknown_backend",
        )
    return factory(**kwargs)


def available_backends() -> List[str]:
    return sorted(_BACKEND_FACTORIES)
