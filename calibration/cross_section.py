# -*- coding: utf-8 -*-
"""M28: CrossSectionEngine — GeometryScene → 2D material profiles.

Produces X-Z / Y-Z cross-sections as material-segmented line profiles,
enabling stable feature-aware metrology (etch depth, CD, sidewall angle).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class MaterialSegment:
    """2D cross-section 中的一个材料段。"""
    mat_id: int
    z_start: float  # nm
    z_end: float    # nm


@dataclass
class CrossSection:
    """一条垂直列的材料分布（沿 z 轴）。"""
    x: float  # nm
    y: float  # nm
    segments: List[MaterialSegment] = field(default_factory=list)


class CrossSectionEngine:
    """从 GeometryScene 的体素化网格提取 2D 材料 profile。"""

    @staticmethod
    def from_voxel_grid(
        grid: np.ndarray,
        voxel_size_nm: float,
        x_index: int,
        y_index: int,
        origin_nm: Tuple[float, float, float] = (0, 0, 0),
    ) -> CrossSection:
        """从体素网格的一个 (x, y) 列提取材料分布。"""
        column = grid[x_index, y_index, :]  # (nz,)
        nz = len(column)
        x_nm = origin_nm[0] + (x_index + 0.5) * voxel_size_nm
        y_nm = origin_nm[1] + (y_index + 0.5) * voxel_size_nm

        segments: List[MaterialSegment] = []
        current_mat = int(column[0])
        seg_start = 0

        for iz in range(1, nz):
            mat = int(column[iz])
            if mat != current_mat:
                z_start = origin_nm[2] + seg_start * voxel_size_nm
                z_end = origin_nm[2] + iz * voxel_size_nm
                segments.append(MaterialSegment(current_mat, z_start, z_end))
                current_mat = mat
                seg_start = iz

        # Final segment
        z_start = origin_nm[2] + seg_start * voxel_size_nm
        z_end = origin_nm[2] + nz * voxel_size_nm
        segments.append(MaterialSegment(current_mat, z_start, z_end))

        return CrossSection(x=x_nm, y=y_nm, segments=segments)

    @staticmethod
    def trench_profile(
        grid: np.ndarray,
        voxel_size_nm: float,
        y_index: int,
        origin_nm: Tuple[float, float, float] = (0, 0, 0),
    ) -> List[CrossSection]:
        """提取沿 x 方向的一行 cross-sections（指定 y）。"""
        nx = grid.shape[0]
        return [
            CrossSectionEngine.from_voxel_grid(
                grid, voxel_size_nm, ix, y_index, origin_nm,
            )
            for ix in range(nx)
        ]

    # ---- Feature-aware metrology on cross-sections ----

    @staticmethod
    def etch_depth(
        profile_before: List[CrossSection],
        profile_after: List[CrossSection],
        material_id: int = 1,
    ) -> float:
        """M28: patterned trench etch depth from cross-sections.

        For each x column, find the top of `material_id` before and after.
        Depth = max descent of the material surface.
        """
        def _top_z(profile: List[CrossSection], mat_id: int) -> List[float]:
            tops = []
            for cs in profile:
                mat_segs = [s for s in cs.segments if s.mat_id == mat_id]
                if mat_segs:
                    tops.append(max(s.z_end for s in mat_segs))
                else:
                    tops.append(float("-inf"))
            return tops

        before_tops = _top_z(profile_before, material_id)
        after_tops = _top_z(profile_after, material_id)

        depths = []
        for bt, at in zip(before_tops, after_tops):
            if bt > float("-inf") and at > float("-inf"):
                depths.append(bt - at)

        return max(depths) if depths else 0.0

    @staticmethod
    def critical_dimension(
        profile: List[CrossSection],
        z_level: float,
        void_id: int = 0,
    ) -> float:
        """CD at specified z_level: total width of void/opening segments."""
        width_voxels = 0
        for cs in profile:
            # Find segment at z_level
            for seg in cs.segments:
                if seg.z_start <= z_level < seg.z_end:
                    if seg.mat_id == void_id:
                        width_voxels += 1
                    break
        return width_voxels  # in voxels (caller × voxel_size_nm)

    @staticmethod
    def sidewall_angle(
        profile: List[CrossSection],
        material_id: int = 1,
        void_id: int = 0,
        z_top: Optional[float] = None,
        z_bottom: Optional[float] = None,
    ) -> float:
        """Sidewall angle from linear fit of material-void boundary.

        Returns angle in degrees (90° = vertical sidewall).
        """
        # Find x positions where material surface transitions
        surface_x = []
        surface_z = []
        for cs in profile:
            # Top of material at this x
            mat_segs = [s for s in cs.segments if s.mat_id == material_id]
            if mat_segs:
                top = max(s.z_end for s in mat_segs)
                if z_top is not None and top > z_top:
                    continue
                if z_bottom is not None and top < z_bottom:
                    continue
                surface_x.append(cs.x)
                surface_z.append(top)

        if len(surface_x) < 2:
            return 90.0  # Cannot determine; assume vertical

        # Linear fit: z = slope * x + intercept
        x_arr = np.array(surface_x)
        z_arr = np.array(surface_z)
        slope = np.polyfit(x_arr, z_arr, 1)[0]

        # Angle from vertical: atan(1/|slope|) in degrees
        if abs(slope) < 1e-10:
            return 0.0  # Horizontal surface
        angle = np.degrees(np.arctan(abs(1.0 / slope)))
        return min(angle, 90.0)
