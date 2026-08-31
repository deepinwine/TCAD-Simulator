# -*- coding: utf-8 -*-
"""冻结 M2 Compatibility API 视图的 dataclass 镜像。

键名与 frontend/src/api/types.ts 逐字段一致（camelCase），序列化结果可直接被
现有 React 客户端消费；迁移到 Pydantic 时按同名字段平移（ADR-013）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

RuntimeStatus = str  # 'ready' | 'dirty' | 'running' | 'done' | 'error'


@dataclass(frozen=True)
class ParameterSpecView:
    key: str
    label: str
    type: str
    default_value: Optional[Any] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Optional[Sequence[Tuple[Any, str]]] = None
    decimals: Optional[int] = None
    step: Optional[float] = None
    units: Optional[str] = None
    tooltip: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return _compact({
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "defaultValue": self.default_value,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "choices": [list(choice) for choice in self.choices] if self.choices is not None else None,
            "decimals": self.decimals,
            "step": self.step,
            "units": self.units,
            "tooltip": self.tooltip,
        })


@dataclass(frozen=True)
class StepView:
    index: int
    name: str
    instanceName: str
    group: str
    loop: str
    enabled: bool
    params: Mapping[str, Any]
    parameterSpecs: Sequence[ParameterSpecView]
    runtimeStatus: RuntimeStatus

    def to_json(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "instanceName": self.instanceName,
            "group": self.group,
            "loop": self.loop,
            "enabled": self.enabled,
            "params": dict(self.params),
            "parameterSpecs": [spec.to_json() for spec in self.parameterSpecs],
            "runtimeStatus": self.runtimeStatus,
        }


@dataclass(frozen=True)
class ModelSummaryView:
    gridShape: Tuple[int, int, int]
    voxelSizeNm: float
    threads: Optional[int] = None
    substrateMaterial: Optional[str] = None
    substrateThicknessNm: Optional[float] = None

    def to_json(self) -> Dict[str, Any]:
        return _compact({
            "gridShape": list(self.gridShape),
            "voxelSizeNm": self.voxelSizeNm,
            "threads": self.threads,
            "substrateMaterial": self.substrateMaterial,
            "substrateThicknessNm": self.substrateThicknessNm,
        })


@dataclass(frozen=True)
class MaterialView:
    id: int
    name: str
    color: Tuple[float, float, float]
    enabled: bool

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "color": list(self.color),
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class InitView:
    recipe: Sequence[StepView]
    model: ModelSummaryView
    factories: Sequence[str]
    materials: Sequence[MaterialView]
    uiState: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return {
            "recipe": [step.to_json() for step in self.recipe],
            "model": self.model.to_json(),
            "factories": list(self.factories),
            "materials": [material.to_json() for material in self.materials],
            "uiState": dict(self.uiState),
        }


@dataclass(frozen=True)
class RunView:
    index: Optional[int] = None
    runtimeStatus: Optional[RuntimeStatus] = None
    modelRevision: Optional[int] = None
    model: Optional[ModelSummaryView] = None
    recipe: Optional[Sequence[StepView]] = None
    log: Optional[Sequence[str]] = None
    skipped: Optional[bool] = None
    reason: Optional[str] = None
    description: Optional[str] = None
    result: Optional[Any] = None

    def to_json(self) -> Dict[str, Any]:
        return _compact({
            "index": self.index,
            "runtimeStatus": self.runtimeStatus,
            "modelRevision": self.modelRevision,
            "model": self.model.to_json() if self.model is not None else None,
            "recipe": [step.to_json() for step in self.recipe] if self.recipe is not None else None,
            "log": list(self.log) if self.log is not None else None,
            "skipped": self.skipped,
            "reason": self.reason,
            "description": self.description,
            "result": self.result,
        })


def to_json(view: Any) -> Dict[str, Any]:
    """按契约键名序列化任一视图对象。"""
    serializer = getattr(view, "to_json", None)
    if callable(serializer):
        return serializer()
    return _compact(asdict(view))


def _compact(payload: Dict[str, Any]) -> Dict[str, Any]:
    """丢弃值为 None 的可选键（契约中可选字段缺省即不出现）。"""
    return {key: value for key, value in payload.items() if value is not None}
