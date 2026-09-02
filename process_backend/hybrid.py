# -*- coding: utf-8 -*-
"""M11：混合 Fast/Accurate 逐工艺模式选择。

`HybridBackend` 按步骤名路由到体素（FAST）或几何（ACCURATE）后端；
跨后端几何交接当前为限制项（见 LIMITATIONS）。
"""
from __future__ import annotations

from typing import Any, Dict

from .base import (
    BackendInfo,
    BackendModelSummary,
    ProcessBackend,
    ProcessBackendError,
    StepOutcome,
)
from .voxel import VoxelBackend

# 默认策略：沉积/CMP/键合/填充走 FAST，刻蚀/光刻走 ACCURATE（可用时）
DEFAULT_MODE_MAP: Dict[str, str] = {
    "Initialize Wafer": "fast",
    "Spin Resist": "fast",
    "Mask Exposure": "fast",
    "Post-Exposure Bake": "fast",
    "Resist Develop": "fast",
    "Etch": "accurate",
    "Selective Epitaxy": "fast",
    "Deposition": "fast",
    "CMP": "fast",
    "Anneal": "fast",
    "Oxidation": "fast",
    "Ion Implantation": "fast",
}

FAST = "fast"
ACCURATE = "accurate"


class ModeSelector:
    """步骤名 → 后端模式映射；unknown 步骤默认 FAST。"""

    def __init__(self, mode_map: Dict[str, str] | None = None) -> None:
        self._map = dict(mode_map or DEFAULT_MODE_MAP)

    def select(self, step_name: str) -> str:
        mode = self._map.get(step_name, FAST)
        if mode == ACCURATE and not _viennaps_ready():
            return FAST  # 引擎缺失时显式回退
        return mode

    def set_mode(self, step_name: str, mode: str) -> None:
        if mode not in (FAST, ACCURATE):
            raise ValueError(f"未知模式：{mode!r}（仅 '{FAST}'/'{ACCURATE}'）")
        self._map[step_name] = mode


def _viennaps_ready() -> bool:
    try:
        import viennaps  # noqa: F401

        return True
    except ImportError:
        return False


class HybridBackend(ProcessBackend):
    """混合后端：按 ModeSelector 路由步骤到 FAST 或 ACCURATE。

    LIMITATIONS（M11 首切片）：
    - 跨后端几何交接未实现（同一配方内切换后端会丢弃前序状态）。
      当前策略：首个 ACCURATE 步骤触发切换后，后续步骤均在该后端执行，
      直至配方结束。完整交接（GeometryScene ↔ level-set/voxel）为 M11 后续。
    - ViennaPS 能力集仅 Initialize Wafer + Etch(Dry)，其余自动回退 FAST。
    """

    def __init__(
        self,
        mode_selector: ModeSelector | None = None,
        grid: int = 64,
        grid_nm: float = 16.0,
    ) -> None:
        self._selector = mode_selector or ModeSelector()
        self._fast = VoxelBackend(grid=grid)
        self._accurate = None  # 惰性创建
        self._active = self._fast
        self._grid_nm = grid_nm
        self._routing_log: list[Dict[str, str]] = []

    @property
    def routing_log(self) -> list[Dict[str, str]]:
        return list(self._routing_log)

    def _get_accurate(self):
        if self._accurate is None:
            from .viennaps_backend import ViennaPSBackend

            self._accurate = ViennaPSBackend(grid_nm=self._grid_nm)
        return self._accurate

    def _switch_to(self, mode: str, step_name: str) -> None:
        if mode == ACCURATE:
            self._active = self._get_accurate()
        else:
            self._active = self._fast
        self._routing_log.append({"step": step_name, "mode": mode})

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="hybrid",
            precision="mixed",
            version="1",
        )

    def summary(self) -> BackendModelSummary:
        return self._active.summary()

    def execute_step(self, step: Any) -> StepOutcome:
        name = str(getattr(step, "name", ""))
        mode = self._selector.select(name)
        self._switch_to(mode, name)
        try:
            return self._active.execute_step(step)
        except ProcessBackendError:
            if mode == ACCURATE:
                # 显式回退到 FAST（记录路由变更）
                self._switch_to(FAST, f"{name} (fallback)")
                return self._fast.execute_step(step)
            raise

    def snapshot(self) -> Any:
        return self._active.snapshot()

    def restore(self, state: Any) -> None:
        self._active.restore(state)

    def material_surfaces(self, face_limit: int = 20000):
        return self._active.material_surfaces(face_limit)

    def grid(self):
        return self._fast.grid()

    def shutdown(self) -> None:
        self._fast.shutdown()
        if self._accurate is not None:
            self._accurate.shutdown()
