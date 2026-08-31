# -*- coding: utf-8 -*-
"""process_api：M4 Python API Facade（ADR-013）。

公共入口：``ProcessCadFacade``、类型化 schema 与 ``ProcessCadError``。
该包只包装既有 runtime，不引入新的工艺物理。
"""
from .errors import ProcessCadError
from .facade import ProcessCadFacade
from .schemas import (
    InitView,
    MaterialView,
    ModelSummaryView,
    ParameterSpecView,
    RunView,
    StepView,
    to_json,
)

__all__ = [
    "InitView",
    "MaterialView",
    "ModelSummaryView",
    "ParameterSpecView",
    "ProcessCadError",
    "ProcessCadFacade",
    "RunView",
    "StepView",
    "to_json",
]
