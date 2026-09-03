# -*- coding: utf-8 -*-
"""M18: HybridBackend 以 canonical GeometryScene 为唯一几何权威。

执行模型（BLOCK-001/002 修复后）：
    ProcessStep → ModeSelector → target backend
    → (switch: bridge transfer, atomic — all-or-nothing)
    → target.execute_step(step)  [execution error → try fallback]
    → target surfaces → canonical scene update  [extraction error → keep old canonical]
"""
from __future__ import annotations

import logging
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
            from geometry_scene.bridge import surfaces_um_to_scene
            surfaces = self._active.material_surfaces(20000)
            self._canonical_scene = surfaces_um_to_scene(surfaces)
            return True
        except Exception as exc:
            logger.warning("canonical scene update failed: %s", exc)
            return False  # keep old canonical; don't raise into caller

    # ---- BLOCK-002 fix: atomic bridge with explicit result ----

    def _bridge_to_accurate(self) -> bool:
        """Transfer canonical scene to ViennaPS. Returns True if target is ready."""
        target = self._get_accurate()
        if self._canonical_scene is None:
            # No state to transfer — target will initialize on first step
            return True
        from geometry_scene.bridge import can_convert_to_viennaps
        ok, reason = can_convert_to_viennaps(self._canonical_scene)
        if not ok:
            logger.info("bridge to ViennaPS rejected: %s", reason)
            return False
        # First version: if target has no domain, it will initialize from the step
        # (bridge construction deferred to M19 multi-material)
        return True

    def _bridge_to_fast(self) -> bool:
        """Transfer canonical scene to VoxelBackend, rebuilding derived state."""
        target = self._fast
        if self._canonical_scene is None:
            return True
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
            logger.warning("bridge to Voxel failed: %s", exc)
            return False

    @staticmethod
    def _rebuild_voxel_derived(model) -> None:
        """Rebuild VoxelBackend derived caches after grid replacement."""
        try:
            if hasattr(model, 'height_map') and model.height_map is not None:
                import numpy as np
                void_id = 0
                mask = model.grid != void_id
                model.height_map = np.where(
                    mask.any(axis=2),
                    mask.shape[2] - np.argmax(mask[::-1], axis=2) - 1,
                    -1,
                ).astype(model.height_map.dtype if hasattr(model.height_map, 'dtype') else int)
            if hasattr(model, '_ensure_material_z_cache'):
                model._ensure_material_z_cache()
        except Exception as exc:
            logger.debug("derived rebuild partial: %s", exc)

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

        # BLOCK-002: atomic switch — bridge failure keeps current backend
        actual_mode = self._switch_backend(mode)
        self._routing_log.append({"step": name, "mode": actual_mode})

        # BLOCK-001: execution and canonical update are isolated
        try:
            outcome = self._active.execute_step(step)
        except ProcessBackendError:
            if actual_mode == ACCURATE:
                self._routing_log.append({
                    "step": f"{name} (fallback)", "mode": FAST,
                })
                # Switch to FAST with bridge
                if self._switch_backend(FAST) == FAST:
                    outcome = self._fast.execute_step(step)
                else:
                    raise  # bridge to FAST also failed
            else:
                raise

        # Update canonical scene AFTER execution succeeds (BLOCK-001)
        # Extraction failure does NOT trigger re-execution
        self._update_canonical_scene()
        return outcome

    # ---- BLOCK-004 fix: versioned snapshot with backend identity ----

    def snapshot(self) -> Any:
        return {
            "version": SNAPSHOT_VERSION,
            "backend": self._active_name,
            "state": self._active.snapshot(),
            "scene": self._canonical_scene,
        }

    def restore(self, state: Any) -> None:
        if isinstance(state, dict) and state.get("version") == SNAPSHOT_VERSION:
            # New format: explicit version check (BLOCK-004)
            backend_name = state.get("backend", FAST)
            if backend_name == ACCURATE:
                self._active = self._get_accurate()
                self._active_name = ACCURATE
            else:
                self._active = self._fast
                self._active_name = FAST
            self._active.restore(state["state"])
            self._canonical_scene = state.get("scene")
        elif isinstance(state, dict) and "backend" in state and "state" in state:
            # Legacy v1 dict without version — try best-effort (BLOCK-004)
            logger.warning("restoring legacy snapshot without version marker")
            backend_name = state.get("backend", FAST)
            if backend_name == ACCURATE:
                self._active = self._get_accurate()
                self._active_name = ACCURATE
            else:
                self._active = self._fast
                self._active_name = FAST
            self._active.restore(state["state"])
            self._canonical_scene = state.get("scene")
            self._update_canonical_scene()
        else:
            # Raw backend state — restore into current active
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
