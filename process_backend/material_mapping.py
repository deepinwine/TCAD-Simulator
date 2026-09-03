# -*- coding: utf-8 -*-
"""M19: 唯一 Material Mapping（BUG-002/003 修复基础）。

MaterialDatabase integer ID ↔ ViennaPS Material enum ↔ GeometryScene mat_id。
单一真相源——所有模块引用此表，禁止各自复制。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def build_mapping(database) -> Dict[int, Any]:
    """MaterialDatabase → {mat_id: viennaps.Material}。惰性构建。"""
    import viennaps as ps

    # ViennaPS Material name → MaterialDatabase name 的标准对应
    _NAME_MAP = {
        "Si": "Silicon",
        "SiO2": "Silicon Dioxide",
        "Si3N4": "Silicon Nitride",
        "PolySi": "Polysilicon",
        "Mask": "Photoresist",  # 近似
        "Air": "Void",
    }
    # 额外的 MaterialDatabase name → ViennaPS Material（名称不完全一致时）
    _EXTRA_MAP = {
        "SiGe": getattr(ps.Material, "SiGe", ps.Material.Si),
        "HfO2": getattr(ps.Material, "HfO2", ps.Material.SiO2),
        "TiN": getattr(ps.Material, "TiN", ps.Material.Si),
        "TaN": getattr(ps.Material, "TaN", ps.Material.Si),
        "SiC": getattr(ps.Material, "SiC", ps.Material.Si),
        "Tungsten": getattr(ps.Material, "W", ps.Material.Si),
        "Copper": getattr(ps.Material, "Cu", ps.Material.Si),
        "Aluminum": getattr(ps.Material, "Al", ps.Material.Si),
    }

    # 反转 name map: DB name → ViennaPS Material
    _db_to_ps: Dict[str, Any] = {}
    for ps_name, db_name in _NAME_MAP.items():
        _db_to_ps[db_name] = getattr(ps.Material, ps_name, None)
    _db_to_ps.update(_EXTRA_MAP)

    mapping: Dict[int, Any] = {}
    for mat_id, material in database.items():
        name = material.name
        if name in _db_to_ps and _db_to_ps[name] is not None:
            mapping[mat_id] = _db_to_ps[name]
        # 未映射的材料不加入——查询时返回 None 而非猜测
    return mapping


def ps_to_mat_id(ps_material, database) -> Optional[int]:
    """ViennaPS Material → MaterialDatabase mat_id。"""
    for mat_id, material in database.items():
        if _ps_name_matches(ps_material, material.name):
            return mat_id
    return None


def _ps_name_matches(ps_material: Any, db_name: str) -> bool:
    """匹配 ViennaPS Material 与 MaterialDatabase name。"""
    ps_name = str(ps_material)
    aliases = {
        "Material('Si')": "Silicon",
        "Material('SiO2')": "Silicon Dioxide",
        "Material('Si3N4')": "Silicon Nitride",
        "Material('PolySi')": "Polysilicon",
        "Material('Mask')": "Photoresist",
        "Material('Air')": "Void",
        "Material('W')": "Tungsten",
        "Material('Cu')": "Copper",
        "Material('Al')": "Aluminum",
        "Material('SiGe')": "SiGe",
        "Material('HfO2')": "HfO2",
        "Material('TiN')": "TiN",
        "Material('TaN')": "TaN",
        "Material('SiC')": "SiC",
    }
    canonical = aliases.get(ps_name, ps_name)
    return canonical == db_name


def name_to_ps_material(name: str) -> Optional[Any]:
    """材料名 → ViennaPS Material。未知返回 None（BUG-003：不默认 SiO2）。"""
    import viennaps as ps

    _name_aliases = {
        "si": "Si", "silicon": "Si", "硅": "Si",
        "sio2": "SiO2", "silicon dioxide": "SiO2", "oxide": "SiO2",
        "二氧化硅": "SiO2", "氧化层": "SiO2",
        "sin": "Si3N4", "si3n4": "Si3N4", "silicon nitride": "Si3N4",
        "氮化硅": "Si3N4", "nitride": "Si3N4",
        "poly": "PolySi", "polysilicon": "PolySi", "多晶硅": "PolySi",
        "pr": "Mask", "photoresist": "Mask", "光刻胶": "Mask",
        "w": "W", "tungsten": "W", "钨": "W",
        "cu": "Cu", "copper": "Cu", "铜": "Cu",
        "tin": "TiN", "titanium nitride": "TiN", "氮化钛": "TiN",
    }
    key = name.strip().lower()
    ps_name = _name_aliases.get(key)
    if ps_name is None:
        return None
    return getattr(ps.Material, ps_name, None)
