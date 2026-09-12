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


def _box_triangles(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Return the closed 12-triangle surface of an axis-aligned box."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    vertices = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=float)
    quads = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    triangles = []
    for a, b, c, d in quads:
        triangles.extend(((vertices[a], vertices[b], vertices[c]),
                          (vertices[a], vertices[c], vertices[d])))
    return np.asarray(triangles)


def uniform_voxel_layers_to_scene(
    grid: np.ndarray,
    voxel_size_nm: float,
    origin_nm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    names: Dict[int, str] | None = None,
) -> GeometryScene:
    """Convert a laterally uniform voxel stack into exact rectangular slabs.

    This is the conservative, lossless Voxel→ViennaPS bridge.  Any lateral
    pattern is rejected instead of being flattened into a blanket layer.
    """
    voxels = np.asarray(grid)
    if voxels.ndim != 3 or any(size <= 0 for size in voxels.shape):
        raise ValueError("voxel grid must be a non-empty 3D array")
    if not np.isfinite(voxel_size_nm) or voxel_size_nm <= 0:
        raise ValueError("voxel size must be finite and positive")

    profile = voxels[0, 0, :]
    if not np.all(voxels == profile[np.newaxis, np.newaxis, :]):
        raise ValueError("patterned voxel geometry cannot be flattened to layers")

    ox, oy, oz = (float(value) for value in origin_nm)
    nx, ny, nz = voxels.shape
    scene = GeometryScene()
    start = 0
    while start < nz:
        mat_id = int(profile[start])
        end = start + 1
        while end < nz and int(profile[end]) == mat_id:
            end += 1
        if mat_id != 0:
            lo = np.array([ox, oy, oz + start * voxel_size_nm])
            hi = np.array([ox + nx * voxel_size_nm,
                           oy + ny * voxel_size_nm,
                           oz + end * voxel_size_nm])
            scene.add(mat_id, _box_triangles(lo, hi), (names or {}).get(mat_id, ""))
        start = end
    return scene


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
    """M27: Vectorized triangle mesh → 3D occupancy (nx,ny,nz).

    For each triangle, computes ray-triangle z-hits for all (ix,iy) grid
    columns simultaneously via numpy broadcasting. ~100x faster than the
    original Python nested loop.
    """
    nx, ny, nz = len(xs), len(ys), len(zs)
    crossings = np.zeros((nx, ny, nz), dtype=bool)
    column_hits = {}
    # Precompute 2D grid for broadcasting
    PX, PY = np.meshgrid(xs, ys, indexing="ij")  # (nx, ny)

    for tri in triangles:
        v0, v1, v2 = tri
        # Bounding box
        lo = np.minimum(np.minimum(v0, v1), v2)
        hi = np.maximum(np.maximum(v0, v1), v2)

        # Grid indices within bounding box (vectorized)
        ix_mask = (xs >= lo[0]) & (xs <= hi[0])
        iy_mask = (ys >= lo[1]) & (ys <= hi[1])
        if not ix_mask.any() or not iy_mask.any():
            continue

        # Edge vectors
        e1 = v1 - v0  # (3,)
        e2 = v2 - v0  # (3,)

        # Möller–Trumbore for ray direction d = +Z = (0,0,1)
        # h = d × e2 = (0,0,1) × (e2x,e2y,e2z) = (-e2y, e2x, 0)
        h = np.array([-e2[1], e2[0], 0.0])
        det = np.dot(e1, h)
        if abs(det) < 1e-12:
            continue
        inv_det = 1.0 / det

        # s = origin - v0; we use s_x = px - v0x, s_y = py - v0y
        SX = PX - v0[0]  # (nx, ny)
        SY = PY - v0[1]  # (nx, ny)

        # u = inv_det * dot(s, h) = inv_det * (s_x*(-e2y) + s_y*(e2x))
        u = inv_det * (SX * h[0] + SY * h[1])

        # q = s × e1 → q_z = s_x * e1_y - s_y * e1_x
        # v = inv_det * dot(d, q) = inv_det * q_z
        v = inv_det * (SX * e1[1] - SY * e1[0])

        # Inside triangle: u >= 0, v >= 0, u + v <= 1
        # (relaxed boundary for numerical precision on diagonal edges)
        eps = 1e-10
        inside = (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps)
        # Restrict to bounding box
        full_mask = np.zeros((nx, ny), dtype=bool)
        full_mask[np.ix_(ix_mask, iy_mask)] = inside[np.ix_(ix_mask, iy_mask)]

        if not full_mask.any():
            continue

        # z_hit = v0_z + u * e1_z + v * e2_z
        z_hit = v0[2] + np.where(full_mask, u, 0) * e1[2] + np.where(full_mask, v, 0) * e2[2]

        # Apply crossings: for each (ix, iy) where inside, flip all zs >= z_hit
        # Vectorized: for each (ix, iy) with a hit, increment crossing count at all z >= z_hit
        hit_indices = np.argwhere(full_mask)
        if hit_indices.size == 0:
            continue

        # Broadcast: crossings[ix, iy, z] += 1 for all z >= z_hit[ix, iy]
        for ix, iy in hit_indices:
            zh = z_hit[ix, iy]
            column_hits.setdefault((ix, iy), []).append(float(zh))

    # Even-odd rule: odd crossing count = inside
    # Adjacent triangles share edges: a ray on the diagonal meets TWO
    # triangles at the SAME surface. Count that surface once, not twice.
    for (ix, iy), hits in column_hits.items():
        ordered = np.sort(hits)
        unique = ordered[np.r_[True, np.diff(ordered) > 1e-8]]
        crossings[ix, iy] = (np.searchsorted(unique, zs, side="right") % 2) == 1
    return crossings


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
) -> List[Tuple[float, int, float, bool]]:
    """GeometryScene → ViennaPS layer list (z_min, mat_id, thickness_nm, is_mask).

    BLOCK-003 fix: validates input before sorting. Rejects:
    - empty meshes
    - non-finite coordinates (NaN/Inf)
    - same material with disconnected layers (gap would be silently filled)
    Returns sorted by z_min ascending.
    Raises ValueError on unsupported topology.
    """
    meshes = scene.meshes
    if not meshes:
        return []

    layers = []
    for mesh in meshes:
        if mesh.triangles.size == 0:
            raise ValueError(
                f"material {mesh.mat_id} has empty mesh; "
                "cannot convert to ViennaPS layers"
            )
        pts = mesh.triangles.reshape(-1, 3)
        # BLOCK-003: reject non-finite coordinates
        if not np.isfinite(pts).all():
            raise ValueError(
                f"material {mesh.mat_id} has non-finite (NaN/Inf) coordinates"
            )
        z_min = float(pts[:, 2].min())
        z_max = float(pts[:, 2].max())
        thickness_nm = z_max - z_min
        if thickness_nm <= 0:
            raise ValueError(
                f"material {mesh.mat_id} has zero/negative thickness "
                f"({thickness_nm}); refusing to silently skip"
            )
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        # Layer reconstruction only represents a complete rectangular slab.
        # Inspect triangles, not mesh count: GeometryScene merges equal IDs.
        face_areas = np.zeros((3, 2))
        for tri in mesh.triangles:
            area = np.linalg.norm(np.cross(tri[1] - tri[0], tri[2] - tri[0])) / 2
            if area <= 1e-10:
                raise ValueError("degenerate triangle in layer")
            faces = [(axis, side) for axis in range(3) for side, edge in enumerate((lo[axis], hi[axis]))
                     if np.allclose(tri[:, axis], edge, atol=1e-7, rtol=0)]
            if len(faces) != 1:
                raise ValueError("patterned or disconnected geometry cannot be flattened to layers")
            face_areas[faces[0]] += area
        dimensions = hi - lo
        expected = np.array([dimensions[1]*dimensions[2], dimensions[0]*dimensions[2], dimensions[0]*dimensions[1]])
        if not np.allclose(face_areas, expected[:, None], rtol=1e-6, atol=1e-7):
            raise ValueError("open, overlapping or incomplete layer faces")
        if layers:
            first_pts = meshes[0].triangles.reshape(-1, 3)
            if not (np.allclose(lo[:2], first_pts.min(axis=0)[:2]) and np.allclose(hi[:2], first_pts.max(axis=0)[:2])):
                raise ValueError("lateral pattern or differing layer footprints cannot be preserved")
        is_mask = mesh.mat_id == 4
        layers.append((z_min, mesh.mat_id, thickness_nm, is_mask))

    # BLOCK-003: detect same-material disconnected layers
    # (would incorrectly fill the gap with one thick layer)
    by_material: Dict[int, List[float]] = {}
    for z_min, mat_id, thickness, _ in layers:
        by_material.setdefault(mat_id, []).append(z_min)
    for mat_id, z_mins in by_material.items():
        if len(z_mins) > 1:
            raise ValueError(
                f"material {mat_id} has {len(z_mins)} disconnected layers "
                f"(z_mins={sorted(z_mins)}); ViennaPS bridge v1 only supports "
                "single contiguous layer per material"
            )

    # BLOCK-003: detect overlapping layers (different materials at same z)
    for i in range(len(layers)):
        for j in range(i + 1, len(layers)):
            z_min_a, _, thick_a, _ = layers[i]
            z_min_b, _, thick_b, _ = layers[j]
            if z_min_a < z_min_b + thick_b and z_min_b < z_min_a + thick_a:
                raise ValueError(
                    f"layers {i} and {j} overlap in z; "
                    "ViennaPS bridge v1 only supports non-overlapping stacks"
                )

    layers.sort(key=lambda layer: layer[0])
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

    try:
        scene_to_viennaps_layers(scene)
    except ValueError as exc:
        return False, str(exc)
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
