# -*- coding: utf-8 -*-
"""GeometryScene：统一双后端几何输出的中立表示（M10，ADR-015）。

VoxelBackend 与 ViennaPSBackend 的 `material_surfaces()` 均可产出
`(mat_id, triangles)` 列表；GeometryScene 以材料为键聚合，提供 STL/VTK 导出。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class MaterialMesh:
    mat_id: int
    name: str = ""
    triangles: np.ndarray = field(default_factory=lambda: np.zeros((0, 3, 3)))

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])


class GeometryScene:
    """材料→网格的场景快照；来源无关（体素或几何后端均可）。"""

    def __init__(self) -> None:
        self._meshes: Dict[int, MaterialMesh] = {}

    @classmethod
    def from_surfaces(
        cls,
        surfaces: List[Tuple[int, np.ndarray]],
        names: Dict[int, str] | None = None,
    ) -> "GeometryScene":
        scene = cls()
        for mat_id, triangles in surfaces:
            scene.add(mat_id, triangles, (names or {}).get(mat_id, ""))
        return scene

    def add(self, mat_id: int, triangles: np.ndarray, name: str = "") -> None:
        tri = np.asarray(triangles, dtype=float)
        if tri.ndim != 3 or tri.shape[1:] != (3, 3):
            tri = tri.reshape(-1, 3, 3)
        if mat_id in self._meshes:
            existing = self._meshes[mat_id].triangles
            self._meshes[mat_id].triangles = np.concatenate([existing, tri], axis=0)
        else:
            self._meshes[mat_id] = MaterialMesh(mat_id=mat_id, name=name, triangles=tri)

    @property
    def meshes(self) -> List[MaterialMesh]:
        return sorted(self._meshes.values(), key=lambda m: m.mat_id)

    @property
    def total_triangles(self) -> int:
        return sum(m.triangle_count for m in self._meshes.values())

    def bounds(self) -> Tuple[float, float, float, float, float, float]:
        all_pts = np.concatenate([m.triangles.reshape(-1, 3) for m in self.meshes])
        lo = all_pts.min(axis=0)
        hi = all_pts.max(axis=0)
        return (float(lo[0]), float(lo[1]), float(lo[2]),
                float(hi[0]), float(hi[1]), float(hi[2]))

    # ---- STL 导出（与既有 /api/preview/stl 兼容的二进制格式） ----

    def export_stl(self, path, mat_id: int | None = None) -> List[Path]:
        targets = ([self._meshes[mat_id]] if mat_id is not None else self.meshes)
        written: List[Path] = []
        for mesh in targets:
            suffix = f"_mat{mesh.mat_id}" if len(self._meshes) > 1 else ""
            out = Path(str(path).replace(".stl", f"{suffix}.stl"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_triangles_to_binary_stl(mesh.triangles))
            written.append(out)
        return written

    # ---- VTK 导出（.vtp polydata，XML 格式） ----

    def export_vtp(self, path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_scene_to_vtp(self))
        return out


def _triangles_to_binary_stl(triangles: np.ndarray) -> bytes:
    tri = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
    if tri.shape[0] == 0:
        raise ValueError("no triangles")
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(lengths, 1e-12)
    records = np.zeros((tri.shape[0], 12), dtype=np.float32)
    records[:, 0:3] = normals
    records[:, 3:12] = tri.reshape(-1, 9)
    out = bytearray()
    out += b"TCAD GeometryScene".ljust(80, b"\0")[:80]
    out += np.uint32(tri.shape[0]).tobytes()
    body = np.zeros(tri.shape[0], dtype=[("f", "<f4", 12), ("attr", "<u2")])
    body["f"] = records
    out += body.tobytes()
    return bytes(out)


def _scene_to_vtp(scene: GeometryScene) -> str:
    """简单的 VTK XML PolyData（多材料合并为一块，material ID 存 cell data）。"""
    meshes = scene.meshes
    if not meshes:
        raise ValueError("empty scene")
    all_tri = np.concatenate([m.triangles for m in meshes], axis=0)
    vertices = all_tri.reshape(-1, 3)
    # 去重顶点
    unique, inverse = np.unique(
        vertices.round(decimals=6), axis=0, return_inverse=True,
    )
    faces = inverse.reshape(-1, 3)
    mat_ids = np.concatenate(
        [np.full(m.triangle_count, m.mat_id, dtype=np.int32) for m in meshes],
    )

    def _xml_tag(tag: str, attrs: str = "", content: str = "") -> str:
        if attrs:
            return f"<{tag} {attrs}>{content}</{tag}>"
        return f"<{tag}>{content}</{tag}>"

    pts = " ".join(f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in unique)
    faces_str = " ".join(
        [f"3 {a} {b} {c}" for a, b, c in faces]
    )
    mats_str = " ".join(str(m) for m in mat_ids)

    return (
        '<?xml version="1.0"?>\n'
        '<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">\n'
        '<PolyData>\n'
        f'<Piece NumberOfPoints="{len(unique)}" NumberOfPolys="{len(faces)}">\n'
        '<Points>\n'
        '<DataArray type="Float64" NumberOfComponents="3" format="ascii">\n'
        f'{pts}\n'
        '</DataArray>\n'
        '</Points>\n'
        '<Polys>\n'
        f'<DataArray type="Int64" Name="connectivity" format="ascii">\n'
        f'{faces_str}\n'
        '</DataArray>\n'
        '</Polys>\n'
        '<CellData>\n'
        f'<DataArray type="Int32" Name="MaterialId" NumberOfComponents="1" format="ascii">\n'
        f'{mats_str}\n'
        '</DataArray>\n'
        '</CellData>\n'
        '</Piece>\n'
        '</PolyData>\n'
        '</VTKFile>\n'
    )
