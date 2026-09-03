# -*- coding: utf-8 -*-
"""M32: Material Registry 2.0 — canonical material definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MaterialVisual:
    color: Tuple[float, float, float]
    opacity: float = 1.0
    metallic: float = 0.0
    roughness: float = 0.72


@dataclass(frozen=True)
class ProcessProperties:
    """Physics-informed process parameters (None = not yet measured)."""
    density_g_cm3: Optional[float] = None
    thermal_conductivity: Optional[float] = None
    relative_permittivity: Optional[float] = None
    bandgap_ev: Optional[float] = None
    electron_affinity_ev: Optional[float] = None
    etch_rate_nm_s: Optional[float] = None  # reference wet etch
    deposition_rate_nm_s: Optional[float] = None  # reference deposition


@dataclass(frozen=True)
class AccurateBackendMapping:
    """ViennaPS material mapping with explicit provenance."""
    viennaps_name: Optional[str] = None
    approximation: bool = False
    reason: str = ""  # e.g. "exact" or "mapped as generic solid"


@dataclass(frozen=True)
class MaterialDefinition:
    """Canonical material definition — single source of truth."""
    id: int
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    category: str = "unknown"  # "semiconductor", "dielectric", "metal", "polymer", "mask"
    visual: MaterialVisual = MaterialVisual(color=(0.5, 0.5, 0.5))
    process: ProcessProperties = ProcessProperties()
    accurate: AccurateBackendMapping = AccurateBackendMapping()

    def matches(self, name: str) -> bool:
        """Case-insensitive match against canonical name and aliases."""
        n = name.strip().lower()
        return n == self.canonical_name.lower() or n in [a.lower() for a in self.aliases]


# ---- Built-in material definitions (IDs match tcad_simulator MaterialDatabase) ----

_BUILTIN: List[MaterialDefinition] = [
    MaterialDefinition(
        id=0, canonical_name="Void", aliases=["air", "vacuum", "空"],
        category="empty",
        visual=MaterialVisual(color=(0, 0, 0), opacity=0),
        accurate=AccurateBackendMapping(viennaps_name="Air", approximation=False),
    ),
    MaterialDefinition(
        id=1, canonical_name="Silicon", aliases=["si", "硅", "单晶硅"],
        category="semiconductor",
        visual=MaterialVisual(color=(0.6, 0.6, 0.65)),
        process=ProcessProperties(density_g_cm3=2.33, bandgap_ev=1.12, relative_permittivity=11.7),
        accurate=AccurateBackendMapping(viennaps_name="Si"),
    ),
    MaterialDefinition(
        id=2, canonical_name="Silicon Dioxide",
        aliases=["sio2", "oxide", "二氧化硅", "氧化层", "氧化硅"],
        category="dielectric",
        visual=MaterialVisual(color=(0.94, 0.94, 0.98)),
        process=ProcessProperties(density_g_cm3=2.65, relative_permittivity=3.9, bandgap_ev=8.9),
        accurate=AccurateBackendMapping(viennaps_name="SiO2"),
    ),
    MaterialDefinition(
        id=3, canonical_name="Silicon Nitride",
        aliases=["sin", "si3n4", "氮化硅", "nitride"],
        category="dielectric",
        visual=MaterialVisual(color=(0.35, 0.67, 0.88)),
        process=ProcessProperties(density_g_cm3=3.17, relative_permittivity=7.5, bandgap_ev=5.3),
        accurate=AccurateBackendMapping(viennaps_name="Si3N4"),
    ),
    MaterialDefinition(
        id=4, canonical_name="Photoresist", aliases=["pr", "光刻胶", "光阻", "resist"],
        category="polymer",
        visual=MaterialVisual(color=(0.97, 0.8, 0.25)),
        accurate=AccurateBackendMapping(viennaps_name="Mask", approximation=True, reason="PR mapped to ViennaPS Mask"),
    ),
    MaterialDefinition(
        id=5, canonical_name="Polysilicon", aliases=["poly", "多晶硅", "poly_si"],
        category="semiconductor",
        visual=MaterialVisual(color=(0.5, 0.5, 0.55)),
        accurate=AccurateBackendMapping(viennaps_name="PolySi"),
    ),
    MaterialDefinition(
        id=6, canonical_name="SiGe", aliases=["硅锗", "sige"],
        category="semiconductor",
        visual=MaterialVisual(color=(0.55, 0.4, 0.4)),
        accurate=AccurateBackendMapping(viennaps_name="SiGe"),
    ),
    MaterialDefinition(
        id=7, canonical_name="HfO2", aliases=["hafnium oxide", "氧化铪"],
        category="dielectric",
        visual=MaterialVisual(color=(0.85, 0.92, 0.98)),
        process=ProcessProperties(relative_permittivity=25.0, bandgap_ev=5.7),
        accurate=AccurateBackendMapping(viennaps_name="HfO2"),
    ),
    MaterialDefinition(
        id=8, canonical_name="TiN", aliases=["titanium nitride", "氮化钛"],
        category="metal",
        visual=MaterialVisual(color=(0.55, 0.5, 0.35)),
        process=ProcessProperties(density_g_cm3=5.22),
        accurate=AccurateBackendMapping(viennaps_name="TiN"),
    ),
    MaterialDefinition(
        id=9, canonical_name="TaN", aliases=["tantalum nitride", "氮化钽"],
        category="metal",
        visual=MaterialVisual(color=(0.4, 0.3, 0.3)),
        accurate=AccurateBackendMapping(viennaps_name="TaN"),
    ),
    MaterialDefinition(
        id=10, canonical_name="SiC", aliases=["silicon carbide", "碳化硅"],
        category="semiconductor",
        visual=MaterialVisual(color=(0.25, 0.4, 0.35)),
        accurate=AccurateBackendMapping(viennaps_name="SiC"),
    ),
    MaterialDefinition(
        id=11, canonical_name="Carbon", aliases=["c", "碳"],
        category="semiconductor",
        visual=MaterialVisual(color=(0.1, 0.1, 0.1)),
        accurate=AccurateBackendMapping(),
    ),
    MaterialDefinition(
        id=12, canonical_name="SiON", aliases=["silicon oxynitride", "氧氮化硅"],
        category="dielectric",
        visual=MaterialVisual(color=(0.88, 0.9, 0.85)),
        accurate=AccurateBackendMapping(),
    ),
    MaterialDefinition(
        id=13, canonical_name="Tungsten", aliases=["w", "钨"],
        category="metal",
        visual=MaterialVisual(color=(0.45, 0.45, 0.5)),
        process=ProcessProperties(density_g_cm3=19.25),
        accurate=AccurateBackendMapping(viennaps_name="W"),
    ),
    MaterialDefinition(
        id=14, canonical_name="Copper", aliases=["cu", "铜"],
        category="metal",
        visual=MaterialVisual(color=(0.72, 0.45, 0.2)),
        process=ProcessProperties(density_g_cm3=8.96),
        accurate=AccurateBackendMapping(viennaps_name="Cu"),
    ),
    MaterialDefinition(
        id=15, canonical_name="Aluminum", aliases=["al", "铝"],
        category="metal",
        visual=MaterialVisual(color=(0.75, 0.75, 0.78)),
        process=ProcessProperties(density_g_cm3=2.70),
        accurate=AccurateBackendMapping(viennaps_name="Al"),
    ),
]


class MaterialRegistry:
    """Canonical material registry — single source of truth."""

    def __init__(self) -> None:
        self._by_id: Dict[int, MaterialDefinition] = {}
        self._by_name: Dict[str, MaterialDefinition] = {}
        for mat in _BUILTIN:
            self.register(mat)

    def register(self, mat: MaterialDefinition) -> None:
        self._by_id[mat.id] = mat
        self._by_name[mat.canonical_name.lower()] = mat
        for alias in mat.aliases:
            self._by_name.setdefault(alias.lower(), mat)

    def get_by_id(self, mat_id: int) -> Optional[MaterialDefinition]:
        return self._by_id.get(mat_id)

    def get_by_name(self, name: str) -> Optional[MaterialDefinition]:
        return self._by_name.get(name.strip().lower())

    def resolve(self, query: str | int) -> Optional[MaterialDefinition]:
        """Resolve by ID or name."""
        if isinstance(query, int):
            return self.get_by_id(query)
        return self.get_by_name(query)

    def all_materials(self) -> List[MaterialDefinition]:
        return sorted(self._by_id.values(), key=lambda m: m.id)

    def materials_by_category(self, category: str) -> List[MaterialDefinition]:
        return [m for m in self.all_materials() if m.category == category]

    @property
    def accurate_supported(self) -> List[MaterialDefinition]:
        """Materials with exact ViennaPS mapping (no approximation)."""
        return [
            m for m in self.all_materials()
            if m.accurate.viennaps_name is not None
            and not m.accurate.approximation
        ]


_registry: Optional[MaterialRegistry] = None


def get_registry() -> MaterialRegistry:
    """Get singleton registry."""
    global _registry
    if _registry is None:
        _registry = MaterialRegistry()
    return _registry
