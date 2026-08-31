# -*- coding: utf-8 -*-
"""ProcessCadFacade：现有 runtime 之上的类型化会话 API（M4，ADR-013）。

只做薄包装与状态跟踪，工艺物理全部委托既有架构契约：
``Recipe -> PROCESS_STEP_FACTORIES -> ProcessStep.execute(model) -> ProcessModel``。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .errors import ProcessCadError
from .schemas import (
    InitView,
    MaterialView,
    ModelSummaryView,
    ParameterSpecView,
    RunView,
    StepView,
)

PHYSICAL_EXTENT_NM = 640.0


class ProcessCadFacade:
    """单会话 facade：一个配方 + 一个模型 + 运行状态跟踪。

    线程安全性：非线程安全；每个会话独立实例（与 WebUISession 语义一致）。
    """

    def __init__(
        self,
        grid: int = 64,
        physical_extent_nm: float = PHYSICAL_EXTENT_NM,
    ) -> None:
        import tcad_simulator as tcad

        self._tcad = tcad
        self._grid = max(32, int(grid))
        self._voxel_nm = float(physical_extent_nm) / self._grid
        self._grid_shape: Tuple[int, int, int] = (self._grid, self._grid, self._grid)
        self._database = tcad.MaterialDatabase()
        self._blobs: List[Dict[str, Any]] = []
        self._statuses: Dict[int, str] = {}
        self._model: Optional[Any] = None
        self._revision = 0

    # ---- 装载 -----------------------------------------------------------

    def load_demo(self, name: str) -> None:
        flows = self._tcad.load_demo_flows(self._database)
        if name not in flows:
            raise ProcessCadError(
                f"未知演示配方：{name!r}",
                code="unknown_demo",
                suggestion=f"可用配方：{sorted(flows)}",
            )
        self._blobs = [dict(blob) for blob in flows[name].get("steps", [])]
        self._reset()

    def load_recipe_blob(self, blob: Dict[str, Any]) -> None:
        steps = blob.get("steps") if isinstance(blob, dict) else None
        if not isinstance(steps, list):
            raise ProcessCadError(
                "配方载荷缺少 steps 列表",
                code="invalid_recipe",
            )
        self._blobs = [dict(step) for step in steps]
        self._reset()

    def _reset(self) -> None:
        if self._model is not None:
            try:
                self._model.parallel.shutdown()
            except Exception:
                pass
        self._model = self._tcad.ProcessModel(
            self._database,
            grid_shape=self._grid_shape,
            voxel_size_nm=self._voxel_nm,
            max_workers=1,
        )
        self._statuses = {}
        for position in range(len(self._blobs)):
            self._statuses[position] = "ready"
        self._revision = 0

    # ---- 视图 -----------------------------------------------------------

    def init(self) -> InitView:
        return InitView(
            recipe=list(self.recipe()),
            model=self.model_summary(),
            factories=self.factories(),
            materials=self.materials(),
            uiState={},
        )

    def recipe(self) -> List[StepView]:
        self._ensure_loaded()
        views: List[StepView] = []
        for position, blob in enumerate(self._blobs):
            step = self._deserialize(position)
            assert step is not None
            views.append(self._step_view(position, blob, step))
        return views

    def model_summary(self) -> ModelSummaryView:
        self._ensure_model()
        assert self._model is not None
        return ModelSummaryView(
            gridShape=self._grid_shape,
            voxelSizeNm=self._voxel_nm,
        )

    def factories(self) -> List[str]:
        return sorted(self._tcad.PROCESS_STEP_FACTORIES.keys())

    def materials(self) -> List[MaterialView]:
        enabled_map: Dict[int, bool] = dict(
            getattr(self._database, "_id_enabled", {}),
        )
        views: List[MaterialView] = []
        for material_id, material in self._database.items():
            views.append(MaterialView(
                id=int(material_id),
                name=str(material.name),
                color=tuple(float(channel) for channel in material.color),
                enabled=bool(enabled_map.get(int(material_id), True)),
            ))
        return views

    def model_revision(self) -> int:
        return self._revision

    # ---- 运行 -----------------------------------------------------------

    def run_step(self, index: int) -> RunView:
        self._ensure_loaded()
        if int(index) not in self._statuses:
            raise ProcessCadError(
                f"步骤索引越界：{index}",
                code="unknown_step",
                step_index=int(index) if isinstance(index, int) else None,
            )
        position = int(index)
        step = self._deserialize(position)
        if step is None:
            raise ProcessCadError(
                f"步骤反序列化失败：{self._blobs[position].get('name')!r}",
                code="invalid_step",
                step_index=position,
            )
        if not bool(self._blobs[position].get("enabled", True)):
            self._statuses[position] = "done"
            return RunView(
                index=position,
                runtimeStatus="done",
                modelRevision=self._revision,
                skipped=True,
                reason="disabled",
            )
        self._statuses[position] = "running"
        try:
            step.execute(self._model)
        except Exception as exc:  # noqa: BLE001 - 契约要求结构化错误而非崩溃
            self._statuses[position] = "error"
            raise ProcessCadError(
                str(exc),
                code="step_failed",
                step_index=position,
                suggestion="Review the step parameters and retry.",
            ) from exc
        self._statuses[position] = "done"
        self._mark_later_dirty(position)
        self._revision += 1
        return RunView(
            index=position,
            runtimeStatus="done",
            modelRevision=self._revision,
        )

    def run_all(self) -> RunView:
        self._ensure_loaded()
        last: Optional[RunView] = None
        for position in range(len(self._blobs)):
            if not bool(self._blobs[position].get("enabled", True)):
                continue
            last = self.run_step(position)
        if last is None:
            raise ProcessCadError(
                "配方没有可执行步骤",
                code="empty_recipe",
            )
        return RunView(
            index=last.index,
            runtimeStatus="done",
            modelRevision=self._revision,
            recipe=list(self.recipe()),
        )

    # ---- 观测辅助（parity / 诊断） ---------------------------------------

    def occupied_voxels(self) -> int:
        self._ensure_model()
        assert self._model is not None
        void_id = self._void_material_id()
        return int(np.count_nonzero(self._model.grid != void_id))

    def present_material_names(self) -> List[str]:
        self._ensure_model()
        assert self._model is not None
        void_id = self._void_material_id()
        present = {
            int(material_id)
            for material_id in np.unique(self._model.grid)
            if int(material_id) != void_id
        }
        return sorted(
            self._database.material(material_id).name for material_id in present
        )

    # ---- 内部 ------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._blobs:
            raise ProcessCadError(
                "尚未装载配方；先调用 load_demo 或 load_recipe_blob",
                code="no_recipe",
            )

    def _ensure_model(self) -> None:
        self._ensure_loaded()
        if self._model is None:
            self._reset()

    def _deserialize(self, position: int) -> Optional[Any]:
        step = self._tcad._webui_deserialize_step(self._blobs[position], self._database)
        if step is not None and self._blobs[position].get("instance_name") is None:
            step.instance_name = self._blobs[position].get("name", step.name)
        return step

    def _step_view(self, position: int, blob: Dict[str, Any], step: Any) -> StepView:
        raw_specs = step.parameter_specs()
        specs = [
            ParameterSpecView(
                key=str(spec.key),
                label=str(spec.label),
                type=str(spec.type),
                default_value=spec.default,
                minimum=spec.minimum,
                maximum=spec.maximum,
                choices=[
                    (choice[0], choice[1]) for choice in (spec.choices or [])
                ],
                decimals=int(spec.decimals) if spec.decimals is not None else None,
                step=spec.step,
                units=spec.units,
                tooltip=spec.tooltip,
            )
            for spec in raw_specs
        ]
        instance_name = self._tcad._normalize_step_instance_name(
            getattr(step, "instance_name", None), step.name,
        )
        return StepView(
            index=position,
            name=str(step.name),
            instanceName=instance_name,
            group=str(getattr(step, "group", "") or ""),
            loop=str(getattr(step, "loop", "") or ""),
            enabled=bool(getattr(step, "enabled", True)),
            params=dict(getattr(step, "params", {}) or {}),
            parameterSpecs=specs,
            runtimeStatus=self._statuses.get(position, "ready"),
        )

    def _mark_later_dirty(self, position: int) -> None:
        # 契约语义：步骤执行后，其后所有步骤相对新状态失效（dirty），
        # 与服务端 run/step 后 Timeline 显示一致（M2 验收实测）。
        for later in range(position + 1, len(self._blobs)):
            self._statuses[later] = "dirty"

    def _void_material_id(self) -> int:
        for material_id, material in self._database.items():
            if material.name == "Void":
                return int(material_id)
        raise ProcessCadError("材料数据库缺少 Void 材料", code="invalid_database")


__all__ = ["ProcessCadFacade", "PHYSICAL_EXTENT_NM"]
