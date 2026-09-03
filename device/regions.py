# -*- coding: utf-8 -*-
"""M33: Device Region Definitions — source/drain/gate/body/electrode/contact."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np


class RegionType(Enum):
    """器件区域类型（标准 TCAD 分类）。"""
    SOURCE = "source"
    DRAIN = "drain"
    GATE = "gate"
    BODY = "body"
    CHANNEL = "channel"
    SDE = "source_drain_extension"  # Source/Drain Extension
    SPACER = "spacer"
    STI = "sti"  # Shallow Trench Isolation
    CONTACT = "contact"
    ELECTRODE = "electrode"
    WELL = "well"
    BURIED_OXIDE = "buried_oxide"
    CUSTOM = "custom"


@dataclass(frozen=True)
class RegionBounds:
    """轴对齐长方体区域边界（nm）。"""
    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float

    def contains(self, x: float, y: float, z: float) -> bool:
        return (self.x_min <= x <= self.x_max
                and self.y_min <= y <= self.y_max
                and self.z_min <= z <= self.z_max)

    def to_dict(self) -> Dict[str, float]:
        return {
            "x_min": self.x_min, "y_min": self.y_min, "z_min": self.z_min,
            "x_max": self.x_max, "y_max": self.y_max, "z_max": self.z_max,
        }


@dataclass
class DeviceRegionDefinition:
    """单个器件区域的定义。

    一个区域由 bounds + 材料 ID + 类型 + 电学角色组成。
    """
    name: str
    region_type: RegionType
    bounds: RegionBounds
    material_ids: List[int] = field(default_factory=list)  # GeometryScene mat_ids
    electrical_role: str = ""  # "ohmic_contact", "schottky", "gate_dielectric", etc.
    doping_type: str = ""  # "n+", "p+", "n", "p", ""
    doping_concentration_cm3: Optional[float] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.region_type.value,
            "bounds": self.bounds.to_dict(),
            "material_ids": self.material_ids,
            "electrical_role": self.electrical_role,
            "doping": {
                "type": self.doping_type,
                "concentration_cm3": self.doping_concentration_cm3,
            },
            "metadata": self.metadata,
        }


@dataclass
class DeviceDefinition:
    """完整器件定义——多个区域的集合 + 电极/边界条件。"""
    name: str = "device"
    regions: List[DeviceRegionDefinition] = field(default_factory=list)
    electrode_boundaries: List[Dict] = field(default_factory=list)

    def add_region(self, region: DeviceRegionDefinition) -> None:
        self.regions.append(region)

    def add_electrode(
        self,
        name: str,
        voltage: float = 0.0,
        region_names: Optional[List[str]] = None,
    ) -> None:
        """添加电极边界条件。"""
        self.electrode_boundaries.append({
            "name": name,
            "type": "dirichlet",
            "value_v": voltage,
            "regions": region_names or [],
        })

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "regions": [r.to_dict() for r in self.regions],
            "electrodes": self.electrode_boundaries,
        }
