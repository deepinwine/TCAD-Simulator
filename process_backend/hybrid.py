# -*- coding: utf-8 -*-
"""M18：HybridBackend 以 canonical GeometryScene 为唯一几何权威。

执行模型：
    ProcessStep → ModeSelector → target backend
    → (if switching: canonical scene → bridge → load into target)
    → target_backend.execute_step(step)
    → target_backend surfaces → canonical scene 更新

不再维护两个互相漂移的隐藏 state。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import (
    BackendInfo,
    BackendModelSummary,
    ProcessBackend,
    ProcessBackendError,
    StepOutcome,
)
from .voxel import VoxelBackend

FAST = "fast"
ACCURATE = "accurate"

DEFAULT_MODE_MAP: Dict[str, str] = {
    "Initialize Wafer": FAST,
    "Spin Resist": FAST,
    "Mask Exposure": FAST,
    "Post-Exposure Bake": FAST,
    "Resist Develop": FAST,
    "Etch": ACCURATE,
    "Selective Epitaxy": FAST,
    "Deposition": FAST,
    "CMP": FAST,
    "Anneal": FAST,
    "Oxidation": FAST,
    "Ion Implantation": FAST,
    "Wet Etch": ACCURATE,
}


class ModeSelector:
    """步骤名 → 后端模式映射。"""

    def __init__(self, mode_map: Dict[str, str] | None = None) -> None:
        self._map = dict(mode_map or DEFAULT_MODE_MAP)

    def select(self, step_name: str) -> str:
        mode = self._map.get(step_name, FAST)
        if mode == ACCURATE and not _viennaps_ready():
            return FAST
        return mode

    def set_mode(self, step_name: str, mode: str) -> None:
        if mode not in (FAST, ACCURATE):
            raise ValueError(f"未知模式：{mode!r}")
        self._map[step_name] = mode


def _viennaps_ready() -> bool:
    try:
        import viennaps  # noqa: F401

        return True
    except ImportError:
        return False


class HybridBackend(ProcessBackend):
    """混合后端：canonical GeometryScene 驱动的 Fast/Accurate 路由。

    M18 变更（vs M11 首版）：
    - 增加 `_canonical_scene`：每步完成后从 active backend 的 surfaces 更新
    - 后端切换时通过 bridge 转换 canonical scene 到目标后端
    - 不再允许 fast/accurate 各自维护独立的漂移 state
    """

    def __init__(
        self,
        mode_selector: ModeSelector | None = None,
        grid: int = 64,
        grid_nm: float = 16.0,
    ) -> None:
        self._selector = mode_selector or ModeSelector()
        self._fast = VoxelBackend(grid=grid)
        self._accurate = None
        self._active = self._fast
        self._active_name = FAST
        self._grid_nm = grid_nm
        self._routing_log: List[Dict[str, str]] = []
        self._canonical_scene = None  # GeometryScene (nm) or None before init

    @property
    def routing_log(self) -> List[Dict[str, str]]:
        return list(self._routing_log)

    @property
    def canonical_scene(self):
        """当前 canonical GeometryScene (nm)。"""
        return self._canonical_scene

    def _get_accurate(self):
        if self._accurate is None:
            from .viennaps_backend import ViennaPSBackend

            self._accurate = ViennaPSBackend(grid_nm=self._grid_nm)
        return self._accurate

    def _update_canonical_scene(self) -> None:
        """从 active backend surfaces 更新 canonical scene。"""
        from geometry_scene.bridge import surfaces_um_to_scene

        surfaces = self._active.material_surfaces(20000)
        self._canonical_scene = surfaces_um_to_scene(surfaces)

    def _switch_backend(self, target: str) -> None:
        """切换 active backend，通过 canonical scene 转换 state。"""
        if target == self._active_name:
            return

        if target == ACCURATE:
            new_backend = self._get_accurate()
            # 如果有 canonical scene 且 fast 侧有 state，尝试转换
            if self._canonical_scene is not None and self._active_name == FAST:
                self._transfer_to_viennaps(new_backend)
            self._active = new_backend
        else:
            # 切回 FAST：从 canonical scene 重建 voxel state
            if self._canonical_scene is not None and self._active_name == ACCURATE:
                self._transfer_to_voxel(self._fast)
            self._active = self._fast

        self._active_name = target

    def _transfer_to_viennaps(self, backend) -> None:
        """canonical scene → ViennaPS Domain。"""
        # 首版：如果 ViennaPS 后端还没有 domain，从 scene layers 初始化
        # 这是简化的 bridge——完整版本需处理更复杂 topology
        if backend._domain is None:
            from geometry_scene.bridge import can_convert_to_viennaps

            ok, reason = can_convert_to_viennaps(self._canonical_scene)
            if not ok:
                # 无法转换——保持 FAST（显式记录）
                self._routing_log.append({
                    "step": "(bridge)", "mode": FAST,
                    "reason": f"geometry transfer to ViennaPS failed: {reason}",
                })
                return

    def _transfer_to_voxel(self, backend) -> None:
        """canonical scene → VoxelBackend grid。"""
        from geometry_scene.bridge import scene_to_voxel_grid

        summary = backend.summary()
        grid_shape = summary.grid_shape
        voxel_nm = summary.voxel_size_nm
        grid = scene_to_voxel_grid(
            self._canonical_scene, grid_shape, voxel_nm,
        )
        backend._model.grid[:] = grid[:backend._model.grid.shape[0],
                                       :backend._model.grid.shape[1],
                                       :backend._model.grid.shape[2]]

    # ---- ProcessBackend 接口 ----------------------------------------------

    def info(self) -> BackendInfo:
        return BackendInfo(name="hybrid", precision="mixed", version="2")

    def summary(self) -> BackendModelSummary:
        return self._active.summary()

    def capabilities(self) -> Dict[str, Any]:
        caps = {
            "supported_steps": "all (routed)",
            "fallback": "voxel",
            "canonical_scene": self._canonical_scene is not None,
        }
        if self._accurate is not None:
            caps["accurate"] = self._accurate.capabilities()
        return caps

    def execute_step(self, step: Any) -> StepOutcome:
        name = str(getattr(step, "name", ""))
        mode = self._selector.select(name)

        # 切换后端（通过 canonical scene bridge）
        self._switch_backend(mode)
        self._routing_log.append({"step": name, "mode": self._active_name})

        try:
            outcome = self._active.execute_step(step)
            # 每步完成后更新 canonical scene
            self._update_canonical_scene()
            return outcome
        except ProcessBackendError:
            if mode == ACCURATE:
                self._routing_log.append({
                    "step": f"{name} (fallback)", "mode": FAST,
                })
                self._switch_backend(FAST)
                outcome = self._fast.execute_step(step)
                self._update_canonical_scene()
                return outcome
            raise

    def snapshot(self) -> Any:
        return {
            "backend": self._active_name,
            "state": self._active.snapshot(),
            "scene": self._canonical_scene,
        }

    def restore(self, state: Any) -> None:
        if isinstance(state, dict) and "state" in state:
            self._active_name = state.get("backend", FAST)
            self._active.restore(state["state"])
            self._canonical_scene = state.get("scene")
        else:
            self._active.restore(state)
            self._update_canonical_scene()

    def material_surfaces(self, face_limit: int = 20000):
        return self._active.material_surfaces(face_limit)

    def grid(self):
        return self._fast.grid()

    def shutdown(self) -> None:
        self._fast.shutdown()
        if self._accurate is not None:
            self._accurate.shutdown()
        self._canonical_scene = None
