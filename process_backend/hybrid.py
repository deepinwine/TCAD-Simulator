# -*- coding: utf-8 -*-
"""M18: HybridBackend 以 canonical GeometryScene 为唯一几何权威。

执行模型（BLOCK-001/002 修复后）：
    ProcessStep → ModeSelector → target backend
    → (switch: bridge transfer, atomic — all-or-nothing)
    → target.execute_step(step)  [execution error → try fallback]
    → target surfaces → canonical scene update  [any failure → rollback]
"""
from __future__ import annotations

import logging
import copy
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    BackendInfo,
    BackendModelSummary,
    ProcessBackend,
    ProcessBackendError,
    StepOutcome,
)
from .voxel import VoxelBackend

logger = logging.getLogger(__name__)

FAST = "fast"
ACCURATE = "accurate"

SNAPSHOT_VERSION = 2  # BLOCK-004: versioned format

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
    """混合后端：canonical GeometryScene 驱动的 Fast/Accurate 路由。"""

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
        self._canonical_scene = None

    @property
    def routing_log(self) -> List[Dict[str, str]]:
        return list(self._routing_log)

    @property
    def canonical_scene(self):
        return self._canonical_scene

    def _get_accurate(self):
        if self._accurate is None:
            from .viennaps_backend import ViennaPSBackend
            self._accurate = ViennaPSBackend(grid_nm=self._grid_nm)
        return self._accurate

    # ---- BLOCK-001 fix: canonical update isolated from execution ----

    def _update_canonical_scene(self) -> bool:
        """Try to update canonical scene; returns success. Never raises."""
        try:
            from geometry_scene.bridge import surfaces_um_to_scene, uniform_voxel_layers_to_scene
            if self._active is self._fast:
                try:
                    names = {mid: material.name for mid, material in self._fast.database.items()}
                    self._canonical_scene = uniform_voxel_layers_to_scene(
                        self._fast.grid(), self._fast.summary().voxel_size_nm, names=names,
                    )
                    return True
                except ValueError:
                    # Patterned voxel geometry remains renderable as a mesh, but
                    # can_convert_to_viennaps() will reject it for backend transfer.
                    pass
            surfaces = self._active.material_surfaces(20000)
            self._canonical_scene = surfaces_um_to_scene(surfaces)
            return True
        except Exception as exc:
            logger.warning("canonical scene update failed: %s", exc)
            return False  # keep old canonical; don't raise into caller

    # ---- BLOCK-002 fix: atomic bridge with explicit result ----

    def _bridge_to_accurate(self) -> bool:
        """M25: Transfer canonical scene to ViennaPS Domain via load_geometry_scene."""
        try:
            target = self._get_accurate()
            if self._canonical_scene is None:
                if not self._update_canonical_scene():
                    return False
            target.load_geometry_scene(self._canonical_scene)
            return True
        except Exception as exc:
            logger.info("bridge to ViennaPS rejected: %s", exc)
            self._routing_log.append({
                "step": "(bridge)", "mode": FAST,
                "reason": f"geometry import failed: {getattr(exc, 'code', 'engine_error')}: {exc}",
            })
            return False

    def _bridge_to_fast(self) -> bool:
        """Transfer canonical scene to VoxelBackend, rebuilding derived state."""
        target = self._fast
        if self._canonical_scene is None:
            return False
        before = target.snapshot()
        try:
            from geometry_scene.bridge import scene_to_voxel_grid
            summary = target.summary()
            grid = scene_to_voxel_grid(
                self._canonical_scene,
                summary.grid_shape,
                summary.voxel_size_nm,
            )
            # Atomically replace grid and rebuild derived caches
            model = target._model
            model.grid[:] = grid[:model.grid.shape[0],
                                 :model.grid.shape[1],
                                 :model.grid.shape[2]]
            # Rebuild height map and other derived caches (BLOCK-002: not just grid)
            self._rebuild_voxel_derived(model)
            return True
        except Exception as exc:
            target.restore(before)
            logger.warning("bridge to Voxel failed: %s", exc)
            return False

    @staticmethod
    def _rebuild_voxel_derived(model) -> None:
        """Use native occupied-layer count (top index + 1, empty = 0)."""
        model._rebuild_height_map()

    def _switch_backend(self, target: str) -> str:
        """Atomic backend switch. Returns the actual active name after switch."""
        if target == self._active_name:
            return self._active_name

        if target == ACCURATE:
            if not self._bridge_to_accurate():
                self._routing_log.append({
                    "step": "(bridge)", "mode": FAST,
                    "reason": "geometry transfer to ViennaPS rejected; staying FAST",
                })
                return self._active_name  # BLOCK-002: don't switch on failure
            self._active = self._get_accurate()
            self._active_name = ACCURATE
            return ACCURATE
        else:
            if not self._bridge_to_fast():
                self._routing_log.append({
                    "step": "(bridge)", "mode": self._active_name,
                    "reason": "geometry transfer to Voxel failed; staying on current",
                })
                return self._active_name
            self._active = self._fast
            self._active_name = FAST
            return FAST

    # ---- ProcessBackend interface ----

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
        before = self.snapshot()
        try:
            actual_mode = self._switch_backend(mode)
            self._routing_log.append({"step": name if actual_mode == mode else f"{name} (fallback)", "mode": actual_mode})
            try:
                outcome = self._active.execute_step(step)
            except ProcessBackendError:
                if actual_mode != ACCURATE:
                    raise
                # Retry only execution failure, and only from the pre-step state.
                self.restore(before)
                self._routing_log.append({"step": f"{name} (fallback)", "mode": FAST})
                if self._switch_backend(FAST) == FAST:
                    outcome = self._fast.execute_step(step)
                else:
                    raise
            if not self._update_canonical_scene():
                raise ProcessBackendError("几何提取失败，已撤销本步骤", code="canonical_update_failed")
            return outcome
        except Exception:
            self.restore(before)
            raise

    # ---- BLOCK-004 fix: versioned snapshot with backend identity ----

    def snapshot(self) -> Any:
        return {
            "version": SNAPSHOT_VERSION,
            "backend": self._active_name,
            "state": self._active.snapshot(),
            "scene": copy.deepcopy(self._canonical_scene),
        }

    def restore(self, state: Any) -> None:
        wrapped = isinstance(state, dict) and ("backend" in state or "version" in state)
        if wrapped:
            if state.get("version", SNAPSHOT_VERSION) != SNAPSHOT_VERSION or state.get("backend") not in (FAST, ACCURATE) or "state" not in state:
                raise ProcessBackendError("无效或不支持的快照格式", code="invalid_snapshot")
            name, raw = state["backend"], state["state"]
        else:
            # Legacy raw voxel dicts belong to FAST, never the current ViennaPS domain.
            name = FAST if isinstance(state, dict) else ACCURATE
            raw = state
        target = self._fast if name == FAST else self._get_accurate()
        previous = target.snapshot() if name == FAST or target._domain is not None else None
        old_active, old_name, old_scene = self._active, self._active_name, self._canonical_scene
        try:
            target.restore(raw)
            self._active, self._active_name = target, name
            if wrapped and "scene" in state:
                self._canonical_scene = copy.deepcopy(state["scene"])
            elif not self._update_canonical_scene():
                raise ProcessBackendError("快照几何提取失败", code="invalid_snapshot")
        except Exception:
            if previous is not None:
                target.restore(previous)
            self._active, self._active_name, self._canonical_scene = old_active, old_name, old_scene
            raise

    def material_surfaces(self, face_limit: int = 20000):
        return self._active.material_surfaces(face_limit)

    def grid(self):
        return self._fast.grid()

    def shutdown(self) -> None:
        self._fast.shutdown()
        if self._accurate is not None:
            self._accurate.shutdown()
        self._canonical_scene = None
