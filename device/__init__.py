# -*- coding: utf-8 -*-
"""M33: Device Mesh / Electrical Solver Interface.

Process CAD → Device TCAD 桥接：
- DeviceRegionDefinition：source/drain/gate/body/electrode/contact 区域标记
- MeshExporter：GeometryScene → Gmsh/VTK volume mesh
- ElectrodeBoundary：边界条件定义
- DeviceSolverBackend：求解器接口 stub（DEVSIM/FEniCSx 适配器预留）
"""
from .regions import DeviceRegionDefinition, RegionType
from .mesh_export import MeshExporter
from .solver import DeviceSolverBackend, SolverResult

__all__ = [
    "DeviceRegionDefinition",
    "DeviceSolverBackend",
    "MeshExporter",
    "RegionType",
    "SolverResult",
]
