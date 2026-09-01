# -*- coding: utf-8 -*-
"""process_backend：M7 ProcessBackend 接口（行为不变的 VoxelBackend 包装）。

公共入口：``ProcessBackend``/``VoxelBackend``/``create_backend`` 与结构化错误。
物理始终委托 ``ProcessStep.execute(model) -> ProcessModel``（宪法契约）。
"""
from .base import (
    BackendInfo,
    BackendModelSummary,
    ProcessBackend,
    ProcessBackendError,
    StepOutcome,
)
from .viennaps_backend import ViennaPSBackend, engine_available
from .voxel import VoxelBackend, available_backends, create_backend

__all__ = [
    "BackendInfo",
    "BackendModelSummary",
    "ProcessBackend",
    "ProcessBackendError",
    "StepOutcome",
    "ViennaPSBackend",
    "VoxelBackend",
    "engine_available",
    "available_backends",
    "create_backend",
]
