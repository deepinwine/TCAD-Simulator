# -*- coding: utf-8 -*-
"""Facade 错误类型：与冻结契约的错误信封语义对齐。"""
from __future__ import annotations

from typing import Optional


class ProcessCadError(Exception):
    """工艺操作失败的结构化错误。

    code 与契约错误信封的 ``code``/``error_type`` 对应；step_index 与
    parameter_path 用于 UI 定位（与 HTTP 错误载荷同名字段语义一致）。
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        step_index: Optional[int] = None,
        parameter_path: Optional[str] = None,
        suggestion: Optional[str] = None,
        rolled_back: Optional[bool] = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.step_index = step_index
        self.parameter_path = parameter_path
        self.suggestion = suggestion
        self.rolled_back = rolled_back

    def to_json(self) -> dict:
        payload = {
            "ok": False,
            "error": str(self),
            "code": self.code,
        }
        if self.step_index is not None:
            payload["step_index"] = self.step_index
        if self.parameter_path is not None:
            payload["parameter_path"] = self.parameter_path
        if self.suggestion is not None:
            payload["suggestion"] = self.suggestion
        if self.rolled_back is not None:
            payload["rolled_back"] = self.rolled_back
        return payload
