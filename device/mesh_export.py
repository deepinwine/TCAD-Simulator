# -*- coding: utf-8 -*-
"""M33: Mesh Export — GeometryScene → volume mesh for device solvers.

支持 VTK UnstructuredGrid (.vtu) 和 Gmsh (.msh) 格式。
第一版基于体素化网格生成 hexahedral mesh。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


class MeshExporter:
    """从体素网格生成求解器可用的 volume mesh。"""

    @staticmethod
    def voxel_to_vtu(
        grid: np.ndarray,
        voxel_size_nm: float,
        origin_nm: Tuple[float, float, float] = (0, 0, 0),
        output_path: Optional[Path] = None,
    ) -> str:
        """体素网格 → VTK XML UnstructuredGrid (.vtu) 字符串。

        每个 solid 体素 → 一个 hexahedron 元素，材料 ID 存 cell data。
        """
        nx, ny, nz = grid.shape
        ox, oy, oz = origin_nm

        # 收集非空体素
        solid_indices = np.argwhere(grid != 0)
        n_cells = len(solid_indices)

        # 生成顶点：每个 hexahedron 8 个顶点（简化：不去重共享顶点）
        points = []
        cells = []
        material_ids = []

        for i, (ix, iy, iz) in enumerate(solid_indices):
            x = ox + ix * voxel_size_nm
            y = oy + iy * voxel_size_nm
            z = oz + iz * voxel_size_nm
            h = voxel_size_nm / 2.0
            cx, cy, cz = x + h, y + h, z + h

            # 8 corners of hexahedron
            corners = [
                (cx-h, cy-h, cz-h), (cx+h, cy-h, cz-h),
                (cx+h, cy+h, cz-h), (cx-h, cy+h, cz-h),
                (cx-h, cy-h, cz+h), (cx+h, cy-h, cz+h),
                (cx+h, cy+h, cz+h), (cx-h, cy+h, cz+h),
            ]
            base = i * 8
            for c in corners:
                points.append(f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f}")
            cells.append(f"8 {' '.join(str(base+j) for j in range(8))}")
            material_ids.append(str(int(grid[ix, iy, iz])))

        # VTK XML
        vtu = (
            '<?xml version="1.0"?>\n'
            '<VTKFile type="UnstructuredGrid" version="0.1">\n'
            f'<UnstructuredGrid>\n'
            f'<Piece NumberOfPoints="{n_cells * 8}" NumberOfCells="{n_cells}">\n'
            '<Points>\n'
            '<DataArray type="Float64" NumberOfComponents="3" format="ascii">\n'
            + '\n'.join(points) + '\n'
            '</DataArray>\n'
            '</Points>\n'
            '<Cells>\n'
            '<DataArray type="Int64" Name="connectivity" format="ascii">\n'
            + '\n'.join(cells) + '\n'
            '</DataArray>\n'
            '<DataArray type="Int64" Name="offsets" format="ascii">\n'
            + ' '.join(str((i+1)*8) for i in range(n_cells)) + '\n'
            '</DataArray>\n'
            '<DataArray type="UInt8" Name="types" format="ascii">\n'
            + ' '.join('12' for _ in range(n_cells)) + '\n'  # 12 = VTK_HEXAHEDRON
            '</DataArray>\n'
            '</Cells>\n'
            '<CellData>\n'
            '<DataArray type="Int32" Name="MaterialId" format="ascii">\n'
            + ' '.join(material_ids) + '\n'
            '</DataArray>\n'
            '</CellData>\n'
            '</Piece>\n'
            '</UnstructuredGrid>\n'
            '</VTKFile>\n'
        )

        if output_path:
            Path(output_path).write_text(vtu)
        return vtu

    @staticmethod
    def voxel_to_gmsh(
        grid: np.ndarray,
        voxel_size_nm: float,
        origin_nm: Tuple[float, float, float] = (0, 0, 0),
        output_path: Optional[Path] = None,
    ) -> str:
        """体素网格 → Gmsh .msh v2 格式字符串。"""
        nx, ny, nz = grid.shape
        ox, oy, oz = origin_nm

        lines = [
            "$MeshFormat",
            "2.2 0 8",
            "$EndMeshFormat",
            "$PhysicalNames",
        ]

        # Physical names for materials
        unique_mats = sorted(set(int(m) for m in np.unique(grid) if m != 0))
        lines.append(str(len(unique_mats)))
        for mat_id in unique_mats:
            lines.append(f"3 {mat_id} \"material_{mat_id}\"")
        lines.append("$EndPhysicalNames")

        # Nodes (voxel centers + corners for hex)
        solid = np.argwhere(grid != 0)
        n_elem = len(solid)
        node_id = 1
        node_lines = []
        elem_lines = []
        elem_id = 1

        lines.append("$Nodes")
        for ix, iy, iz in solid:
            x = ox + (ix + 0.5) * voxel_size_nm
            y = oy + (iy + 0.5) * voxel_size_nm
            z = oz + (iz + 0.5) * voxel_size_nm
            h = voxel_size_nm / 2.0

            corner_ids = []
            for dx, dy, dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                               (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]:
                px, py, pz = x + dx*h, y + dy*h, z + dz*h
                node_lines.append(f"{node_id} {px:.3f} {py:.3f} {pz:.3f}")
                corner_ids.append(node_id)
                node_id += 1

            mat_id = int(grid[ix, iy, iz])
            elem_lines.append(
                f"{elem_id} 5 {mat_id} " + " ".join(str(c) for c in corner_ids)
            )
            elem_id += 1

        total_nodes = node_id - 1
        lines.insert(-len(node_lines) - 1, str(total_nodes))
        lines.extend(node_lines)
        lines.append("$EndNodes")

        lines.append("$Elements")
        lines.append(str(n_elem))
        lines.extend(elem_lines)
        lines.append("$EndElements")

        msh_content = "\n".join(lines) + "\n"
        if output_path:
            Path(output_path).write_text(msh_content)
        return msh_content
