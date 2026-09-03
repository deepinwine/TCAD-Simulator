# -*- coding: utf-8 -*-
"""M35: TCAD Project Format (.tcad) — portable project package.

一个 .tcad 是一个 zip 包，包含：
  project.json     — 元数据 + recipe + 模式 + 标定引用
  geometry/        — 可选 GeometryScene VTK/STL 快照
  calibration/     — 可选标定 profile JSON
  layout/          — 可选 GDS/OASIS 文件

大型 mesh/voxel 数据单独 binary 文件，不嵌入 JSON。
"""
from .format import ProjectFormat, ProjectMetadata, SimulationModeConfig, load_project, save_project

__all__ = ["ProjectFormat", "ProjectMetadata", "SimulationModeConfig", "load_project", "save_project"]
