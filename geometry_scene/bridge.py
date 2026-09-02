# -*- coding: utf-8 -*-
"""Geometry Bridge（M13）：GeometryScene ↔ Voxel / ViennaPS 双向转换。

单位约定：GeometryScene 内部 **nm**（见 docs/GEOMETRY_BRIDGE.md）；
后端 surface 输出 µm → 本模块 ×1000 统一。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from .scene import GeometryScene, MaterialMesh

UM_TO_NM = 1000.0


def surfaces_um_to_scene(
    surfaces: List[Tuple[int, np.ndarray]],
    names: Dict[int, str] | None = None,
) -> GeometryScene:
    """后端 material_surfaces（µm）→ GeometryScene（nm）。"""
    nm_surfaces = [(mid, tri * UM_TO_NM) for mid, tri in surfaces]
    return GeometryScene.from_surfaces(nm_surfaces, names)


def scene_to_voxel_grid(
    scene: GeometryScene,
    grid_shape: Tuple[int, int, int],
    voxel_size_nm: float,
    origin_nm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """GeometryScene（nm）→ material_id 体素网格。

    体素化：per-material 三角网格 → even-odd 3D 扫描线填充。
    材料 precedence：后到的 mesh 覆盖先到的（模拟 stacked deposition）。
    """
    nx, ny, nz = grid_shape
    grid = np.zeros((nx, ny, nz), dtype=np.uint16)

    ox, oy, oz = origin_nm
    # 体素中心坐标（nm）
    xs = ox + (np.arange(nx) + 0.5) * voxel_size_nm
    ys = oy + (np.arange(ny) + 0.5) * voxel_size_nm
    zs = oz + (np.arange(nz) + 0.5) * voxel_size_nm

    for mesh in scene.meshes:
        occupancy = _voxelize_mesh(mesh.triangles, xs, ys, zs)
        grid[occupancy] = mesh.mat_id

    return grid


def _voxelize_mesh(
    triangles: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
) -> np.ndarray:
    """三角网格 → 3D even-odd 布尔占用（(nx,ny,nz)）。"""
    nx, ny, nz = len(xs), len(ys), len(zs)
    occupancy = np.zeros((nx, ny, nz), dtype=bool)

    # 方法：对每条 (ix, iy) 垂直列，求所有三角形与该列 z 轴的交点，
    # 然后按 even-odd 规则填充。
    # 简化实现：将三角形投影到 (x, y) 平面，对每个 (ix, iy) 列，
    # 计算三角形在 (x,y) 处的 z 值范围（用三角形平面方程）。

    for tri in triangles:
        v0, v1, v2 = tri
        # 三角形包围盒
        lo = np.minimum(np.minimum(v0, v1), v2)
        hi = np.maximum(np.maximum(v0, v1), v2)

        ix_range = np.nonzero((xs >= lo[0]) & (xs <= hi[0]))[0]
        iy_range = np.nonzero((ys >= lo[1]) & (ys <= hi[1]))[0]
        if ix_range.size == 0 or iy_range.size == 0:
            continue

        # 法向量
        normal = np.cross(v1 - v0, v2 - v0)
        norm = np.linalg.norm(normal)
        if norm < 1e-12:
            continue
        normal = normal / norm

        for ix in ix_range:
            for iy in iy_range:
                px, py = xs[ix], ys[iy]
                # 射线-三角形：从 (px, py, -inf) 沿 +Z 方向
                z_hit = _ray_triangle_z(px, py, v0, v1, v2)
                if z_hit is not None:
                    # 该列在此 z 值处有一个 crossing
                    occupancy[ix, iy, :] ^= _column_crossing(zs, z_hit)

    return occupancy


def _column_crossing(zs: np.ndarray, z_hit: float) -> np.ndarray:
    """在 z_hit 处的 crossing → even-odd 翻转 mask。"""
    return (zs >= z_hit).astype(bool)


def _ray_triangle_z(
    px: float,
    py: float,
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
) -> float | None:
    """垂直射线 (px, py, t) 与三角形的 z 交点；无交点返回 None。"""
    # Möller–Trumbore（射线方向 = +Z）
    direction = np.array([0.0, 0.0, 1.0])
    origin = np.array([px, py, -1e12])

    edge1 = v1 - v0
    edge2 = v2 - v0
    h = np.cross(direction, edge2)
    det = np.dot(edge1, h)
    if abs(det) < 1e-12:
        return None

    inv_det = 1.0 / det
    s = origin - v0
    u = inv_det * np.dot(s, h)
    if u < 0.0 or u > 1.0:
        return None

    q = np.cross(s, edge1)
    v = inv_det * np.dot(direction, q)
    if v < 0.0 or u + v > 1.0:
        return None

    t = inv_det * np.dot(edge2, q)
    if t <= 0:
        return None

    return origin[2] + t * direction[2]


def scene_to_viennaps_layers(
    scene: GeometryScene,
) -> List[Tuple[float, int, bool]]:
    """GeometryScene → ViennaPS MakeTrench.MaterialLayer 列表。

    第一版仅支持「从下到上的 stacked conformal layers」。
    返回 [(thickness_nm, mat_id, is_mask), ...]，从 substrate 开始向上。
    不支持的 topology 返回空列表（调用者应报错）。
    """
    meshes = scene.meshes
    if not meshes:
        return []

    # 按 z_min 排序（从下到上）
    layers = []
    for mesh in meshes:
        pts = mesh.triangles.reshape(-1, 3)
        z_min = pts[:, 2].min()
        z_max = pts[:, 2].max()
        thickness_nm = z_max - z_min
        if thickness_nm <= 0:
            continue
        is_mask = mesh.mat_id == 4  # Photoresist 视为 mask
        layers.append((float(thickness_nm), mesh.mat_id, is_mask))

    layers.sort(key=lambda layer: layer[0], reverse=True)  # 厚的在下
    return layers


def can_convert_to_viennaps(scene: GeometryScene) -> Tuple[bool, str]:
    """检查 scene 是否可转换为 ViennaPS level-set stack。"""
    if not scene.meshes:
        return False, "empty scene"
    if len(scene.meshes) > 8:
        return False, f"too many materials ({len(scene.meshes)}); max 8 for first version"

    for mesh in scene.meshes:
        pts = mesh.triangles.reshape(-1, 3)
        if pts.shape[0] < 4:
            return False, f"material {mesh.mat_id} has too few vertices"

    return True, "ok"


# ---- Transfer Error Metrics ----

def transfer_metrics(
    before: GeometryScene,
    after: GeometryScene,
) -> Dict[str, Any]:
    """记录一次 backend 转换前后的几何误差指标。"""
    def _total_volume(meshes: List[MaterialMesh]) -> float:
        total = 0.0
        for mesh in meshes:
            for tri in mesh.triangles:
                v0, v1, v2 = tri
                total += abs(np.dot(v0, np.cross(v1, v2))) / 6.0
        return total

    def _bounds(meshes: List[MaterialMesh]) -> Tuple:
        if not meshes:
            return (0, 0, 0, 0, 0, 0)
        pts = np.concatenate([m.triangles.reshape(-1, 3) for m in meshes])
        return tuple(pts.min(0)) + tuple(pts.max(0))

    before_vol = _total_volume(before.meshes)
    after_vol = _total_volume(after.meshes)
    vol_err = (after_vol - before_vol) / max(before_vol, 1e-9) * 100 if before_vol else 0

    return {
        "before_total_triangles": before.total_triangles,
        "after_total_triangles": after.total_triangles,
        "before_bounds": _bounds(before.meshes),
        "after_bounds": _bounds(after.meshes),
        "volume_error_pct": round(vol_err, 2),
    }
